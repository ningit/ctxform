#
# Test and benchmark the satisfiability checker with various formulas
#
# Uses systemd and Linux's cgroups v2 to limit time and memory usage for each
# test case, so it only works under Linux. systemd 255 or above is required
# to measure the peak memory usage. dbus-python is used to connect with systemd.
#
# The implementation is rudimentary and relies on some unstrustworthy timeouts.
#

import json
import math
import time
from multiprocessing import Process, Pipe, connection

import dbus

from ctxform.logics import PROBLEM_CLASS, PARSER_CLASS
from ctxform.ltl import LTLProblem
from ctxform.parser import Operator as Op


#
# Functions to generate some families of formulas
#

def change_head(formula: tuple):
	"""Change the operator on the head of the formula"""

	head, *args = formula

	match head:
		case Op.WUNTIL:
			new_op = Op.UNTIL
		case Op.UNTIL:
			new_op = Op.WUNTIL
		case _:
			return formula

	return new_op, *args


def nested_formula(n: int, weak: bool = False, m: int = 0):
	"""Nested LTL formula extended from Esparza et al. JACM paper"""

	if n == 0:
		return Op.WUNTIL if weak else Op.UNTIL, (Op.VAR, f'p{m}'), (Op.VAR, f'p{m+1}')
	else:
		recursive = (Op.CTX, f'c{m}', nested_formula(n - 1, not weak, m + 1))
		fixed = (Op.VAR, f'p{m}')

		return (Op.WUNTIL, recursive, fixed) if weak else (Op.UNTIL, fixed, recursive)


def nested_equivalent(n: int, weak: bool = False, m: int = 0):
	"""Reduced nested_formula"""

	if n == 0:
		return nested_formula(0, weak, m)

	elif weak:
		nested = nested_formula(n - 1, not weak, m + 1)

		return (Op.DISJUNCTION,
			(Op.CONJUNCTION,
				(Op.ALWAYS, (Op.EVENTUALLY, nested[2])),
				# The original one with W below
				(Op.WUNTIL,
					(Op.CTX, f'c{m}', change_head(nested)),
					(Op.VAR, f'p{m}'),
				)
			),
			# The original one with U above and something else to the right
			(Op.UNTIL,
				(Op.CTX, f'c{m}', nested_equivalent(n - 1, not weak, m + 1)),
				(Op.DISJUNCTION,
					(Op.VAR, f'p{m}'),
					(Op.ALWAYS, (Op.CTX, f'c{m}', (Op.LIT, False))),
				)
			)
		)

	else:
		nested = nested_formula(n - 1, not weak, m + 1)

		return (Op.DISJUNCTION,
			# The original one with U below
			(Op.UNTIL,
				(Op.VAR, f'p{m}'),
				(Op.CTX, f'c{m}', change_head(nested)),
			),
			(Op.CONJUNCTION,
				(Op.EVENTUALLY, (Op.ALWAYS, nested[1])),
				# The original one with U above and something else to the right
				(Op.WUNTIL,
					(Op.CONJUNCTION,
						(Op.VAR, f'p{m}'),
						(Op.EVENTUALLY, (Op.CTX, f'c{m}', (Op.LIT, True))),
					),
					(Op.CTX, f'c{m}', nested_equivalent(n - 1, not weak, m + 1)),
				),
			)
		)


def fgf_formula(n: int, fg: bool = True, m: int = 0, same: bool = False):
	"""Formulas mixing FG and GF"""

	ctx = 'c' if same else f'c{m}'

	if n == 0:
		return Op.CTX, ctx, (Op.VAR, 'p')
	else:
		first, second = Op.ALWAYS, Op.EVENTUALLY

		if fg:
			first, second = second, first

		return Op.CTX, ctx, (first, (second, fgf_formula(n - 1, not fg, m + 1, same)))


def fgf_equivalent(n: int, fg: bool = True, m: int = 0, same: bool = False):
	"""Equivalent to fgf_formula"""

	ctx = 'c' if same else f'c{m}'

	if n == 0:
		return fgf_formula(n, fg, m, same)
	else:
		first, second = Op.ALWAYS, Op.EVENTUALLY

		if fg:
			first, second = second, first

		return (Op.DISJUNCTION,
			(Op.CONJUNCTION,
				(first, (second, fgf_equivalent(n - 1, not fg, m + 1, same))),
				(Op.CTX, ctx, (Op.LIT, True))
			),
			(Op.CTX, ctx, (Op.LIT, False))
		)


#
# Functions to obtain information about formulas
#

def formula_size(form):
	"""Size of the formula"""

	head, *args = form

	match head:
		case Op.CTX | Op.LIT | Op.VAR:
			return 1
		case _:
			return 1 + sum(formula_size(arg) for arg in args)


def formula_depth(form):
	"""Size of the formula"""

	head, *args = form

	match head:
		case Op.LIT | Op.VAR:
			return 0
		case Op.CTX:
			return 1 + formula_depth(args[1])
		case _:
			return max(formula_depth(arg) for arg in args)


#
# Functions to control resource usage
#

class ControlledRunner:
	"""Run functions in a controlled environment"""

	def __init__(self, memory_limit=4000000000, time_limit=600, scope_name='ctxform-test.scope'):

		# Memory limit in bytes
		self.memory_limit = memory_limit
		# Time limit in seconds
		self.time_limit = time_limit
		# Name of the systemd scope
		self.scope_name = scope_name

		# Connect to the user session bus
		self.bus = dbus.SessionBus()
		systemd = self.bus.get_object('org.freedesktop.systemd1', '/org/freedesktop/systemd1')

		# Check systemd version for compatibility
		version = str(dbus.Interface(systemd, dbus_interface='org.freedesktop.DBus.Properties').Get(
			'org.freedesktop.systemd1.Manager', 'Version'))
		self.recent_enough = int(version.split('.', maxsplit=1)[0]) >= 255

		if not self.recent_enough:
			print(f'Using systemd version {version} while memory peak measurement requires systemd 255 or above.')

		# Manager to connect with the user session systemd
		self.manager = dbus.Interface(systemd, dbus_interface='org.freedesktop.systemd1.Manager')

	def run(self, func, args=()):
		"""Run a function in the controlled environment"""

		# Start the process for the given function
		parent_conn, child_conn = Pipe()
		process = Process(target=self.target, args=(child_conn, func, args))
		process.start()

		properties = [
			('Description', 'Test scope for ctxform'),
			('PIDs', [dbus.UInt32(process.pid)]),
			('MemoryMax', dbus.UInt64(self.memory_limit)),
			('MemorySwapMax', dbus.UInt64(0)),
			# ('RuntimeMaxUSec', dbus.UInt64(self.time_limit * 1000000)),
		]

		# Start a scope where to confine the process and let it go on
		job = self.manager.StartTransientUnit(self.scope_name, 'fail', properties, ())
		job_iface = dbus.Interface(self.bus.get_object('org.freedesktop.systemd1', job),
		                           'org.freedesktop.DBus.Properties')

		# Wait until the unit is active to start the process
		unit = self.bus.get_object('org.freedesktop.systemd1', self.manager.GetUnit('ctxform-test.scope'))
		unit_props = dbus.Interface(unit, 'org.freedesktop.DBus.Properties')

		while unit_props.Get('org.freedesktop.systemd1.Unit', 'ActiveState') != 'active':
			time.sleep(0.25)

		# Send a message to start the actual algorithm (otherwise the process
		# will start unconfined and the measures will be accurate)
		parent_conn.send('start')

		# Wait until the process has finished, successfully or not
		# (process.sentinel signals whether the process has finished,
		# while parent_conn will wake up this when a message is available)
		ready = connection.wait([process.sentinel, parent_conn], timeout=self.time_limit + 1)

		# Process does not finish in time
		if not ready:
			memory_peak = int(unit_props.Get('org.freedesktop.systemd1.Scope', 'MemoryPeak')) if self.recent_enough else -1
			cpu_usage = int(unit_props.Get('org.freedesktop.systemd1.Scope', 'CPUUsageNSec'))

			# Kill the unit
			unit.Kill('all', dbus.UInt32(9), dbus_interface='org.freedesktop.systemd1.Unit')
			time.sleep(5)

			return dict(ok=False, cpu_usage=cpu_usage, memory_peak=memory_peak, reason='timeout')

		# Process has finished successfully
		elif ready[0] != process.sentinel:
			memory_peak = int(unit_props.Get('org.freedesktop.systemd1.Scope', 'MemoryPeak')) if self.recent_enough else -1
			cpu_usage = int(unit_props.Get('org.freedesktop.systemd1.Scope', 'CPUUsageNSec'))

			# Result contains the time measures by the child process
			result = parent_conn.recv()

			# Once the measures have been taken, we signal the process to finish
			parent_conn.send('ok')
			process.join()

			# Wait until the unit gets inactive
			state = str(unit_props.Get('org.freedesktop.systemd1.Unit', 'ActiveState'))

			while state == 'active':
				time.sleep(0.25)
				state = str(unit_props.Get('org.freedesktop.systemd1.Unit', 'ActiveState'))

			return dict(ok=True, cpu_usage=cpu_usage, memory_peak=memory_peak, result=result)

		# Process has failed
		else:
			result = str(unit_props.Get('org.freedesktop.systemd1.Scope', 'Result'))
			cpu_usage = int(unit_props.Get('org.freedesktop.systemd1.Scope', 'CPUUsageNSec'))

			# Reset the failed unit to reuse it with the next test case
			unit.ResetFailed(dbus_interface='org.freedesktop.systemd1.Unit')
			# result would be oom-killer (out of memory)
			print(' ', result)
			# Wait for some time
			time.sleep(5)

			return dict(ok=False, cpu_usage=cpu_usage, reason=result)

	@staticmethod
	def target(conn, func, args):
		"""What gets executed by the child process"""

		# Wait until the scope is set
		conn.recv()

		try:
			result = func(*args)
		except Exception as e:
			result = e

		# Tell the caller that we are ready
		conn.send(result)
		# Wait until the metadata has been captured
		conn.recv()


def benchmark_method1(problem_class, f1, f2):
	"""Benchmark two formulas"""

	problem = problem_class(f1, f2)
	start = time.perf_counter_ns()
	result = problem.solve_with_context(timeout=None)[1]
	end = time.perf_counter_ns()

	extra = {}

	# For LTL, capture the number of automata states
	if problem_class == LTLProblem:
		extra['left-states'] = problem.aut_left.num_states()
		extra['left-not-states'] = problem.aut_not_left.num_states()
		extra['right-states'] = problem.aut_right.num_states()
		extra['right-not-states'] = problem.aut_not_right.num_states()

	return result, end - start, extra


def benchmark_method2(problem_class, f1, f2):
	"""Benchmark two formulas"""

	problem = problem_class(f1, f2)
	start = time.perf_counter_ns()
	result = problem.solve(timeout=None)[0]
	end = time.perf_counter_ns()

	# Obtain the canonical context
	# canonical = problem.canonical_context(simplified=True)
	# if isinstance(canonical, tuple):
	#	canonical = problem.canonical_context(simplified=False)

	# Capture the number of contexts, new variables, and clauses
	extra = {
		'ctx-vars': len(problem.transformer.ctx_map),
		'ctx-occur': len(problem.transformer.ctx_ap_map),
		'cond-clauses': 2 * sum(math.comb(len(group), 2) for group in problem.transformer.ctx_map.values()),
		# 'canonical': str(to_spot(canonical['f']).simplify()) if canonical is not None else '',
	}

	# For LTL, capture the number of automata states
	if problem_class == LTLProblem:
		extra['left-states'] = problem.aut_left.num_states()
		extra['left-not-states'] = problem.aut_not_left.num_states()
		extra['right-states'] = problem.aut_right.num_states()
		extra['right-not-states'] = problem.aut_not_right.num_states()
		extra['cond-states'] = problem.aut_cond.num_states()

	return result, end - start, extra


def dump_result(out, logic: str, name: str, lhs, rhs, mth1, mth2, arg=None):
	"""Dump the result to a ndJSON file"""

	# Common information
	summary = {
		'logic': logic,
		'id': name,
		'arg': arg,
		'lhs': {
			'size': formula_size(lhs),
			'depth': formula_depth(lhs),
		},
		'rhs': {
			'size': formula_size(rhs),
			'depth': formula_depth(rhs),
		},
	}

	# Result of each method
	for k, mth in enumerate((mth1, mth2), start=1):
		if mth is not None:
			if mth['ok']:
				if isinstance(mth['result'], Exception):
					summary[f'mth{k}'] = {
						'ok': False,
						'reason': 'exception',
						'details': str(mth['result']),
					}
				else:
					result, etime, extra = mth['result']

					summary[f'mth{k}'] = {
						'ok': True,
						'result': result,
						'time': etime,
						'cpu': mth['cpu_usage'],
						'memory': mth['memory_peak'],
					} | extra
			else:
				summary[f'mth{k}'] = {
					'ok': False,
					'reason': mth['reason'],
				}

	json.dump(summary, out)
	out.write('\n')
	out.flush()


def load_static_formulas(filename='formulas.json'):
	"""Load formulas from file"""

	# Load formulas from file
	if filename.endswith('.toml'):
		import tomllib
		with open(filename, 'rb') as tf:
			static_forms = tomllib.load(tf)
	else:
		with open(filename, 'rb') as jf:
			static_forms = json.load(jf)

	# Import between logics
	for logic, imports in static_forms.get('import', {}).items():
		for other in imports:
			static_forms[logic] |= static_forms[other]

	static_forms.pop('import')

	return static_forms


def show_info(rid, mth):
	"""Show brief information about a run"""

	msg = f'{mth["cpu_usage"] / 1e9:.2}' if mth['ok'] else mth['reason']
	return f' ({rid}) {msg}'


def main():
	"""Run all tests and benchmarks"""

	import argparse

	args_parser = argparse.ArgumentParser(description='Test runner')
	args_parser.add_argument('--input', '-i', help='JSON/TOML file with formulas', default='test/formulas.json')
	args_parser.add_argument('--output', '-o', help='Path to save the results (ndjson)', default='results.ndjson')
	args_parser.add_argument('--timeout', help='Timeout for executions', type=int, default=900)
	args_parser.add_argument('--memlimit', help='Memory limit (in Mb)', type=int, default=8000)
	args_parser.add_argument('--skip-generated', help='Do not check generated formulas', action='store_true')

	args = args_parser.parse_args()

	# Load static formulas from file
	static_forms = load_static_formulas(args.input)

	# Test written before the case in the terminal
	# pretext = '\x1b[1K\r'
	pretext = '\n'

	# Runner of test cases
	runner = ControlledRunner(time_limit=args.timeout, memory_limit=args.memlimit * 1000000)

	with open(args.output, 'w') as out:
		# Fixed size cases
		for logic, cases in static_forms.items():
			Problem = PROBLEM_CLASS[logic]
			Parser = PARSER_CLASS[logic]

			parser = Parser()

			for name, (lhs, rhs) in cases.items():
				print(f'{pretext}{logic} {name}', end='', flush=True)
				plhs = parser.parse(lhs)
				prhs = parser.parse(rhs)

				mth2 = runner.run(benchmark_method2, args=(Problem, plhs, prhs))
				print(show_info(2, mth2), end='', flush=True)
				mth1 = runner.run(benchmark_method1, args=(Problem, plhs, prhs))
				print(show_info(1, mth1), end='', flush=True)

				dump_result(out, logic, name, plhs, prhs, mth1, mth2)

		# Skip checking generated formulas
		if args.skip_generated:
			return

		# The rest are LTL cases
		Problem = PROBLEM_CLASS['ltl']
		logic = 'ltl'

		# Nested formula
		for k in range(3):
			for weak in (True, False):
				print(f'{pretext}nested {k} {weak}', end='', flush=True)
				f1 = nested_formula(k, weak)
				f2 = nested_equivalent(k, weak)

				mth1 = runner.run(benchmark_method1, args=(Problem, f1, f2))
				print(show_info(1, mth1), end='', flush=True)
				mth2 = runner.run(benchmark_method2, args=(Problem, f1, f2))
				print(show_info(2, mth1), end='', flush=True)

				dump_result(out, logic, 'nested', f1, f2, mth1, mth2, arg={'n': k, 'weak': weak})

		# Nested FG and GF
		for k in range(4):
			for same in (True, False):
				for fg in (True, False):
					print(f'{pretext}fgf {k} {same} {fg}', end='', flush=True)
					f1 = fgf_formula(k, fg=fg, same=same)
					f2 = fgf_equivalent(k, fg=fg, same=same)

					mth1 = runner.run(benchmark_method1, args=(Problem, f1, f2))
					print(show_info(1, mth1), end='', flush=True)
					mth2 = runner.run(benchmark_method2, args=(Problem, f1, f2))
					print(show_info(2, mth2), end='', flush=True)

					dump_result(out, logic, 'fgf', f1, f2, mth1, mth2, arg={'n': k, 'same': same, 'fg': fg})

		print()


if __name__ == '__main__':
	main()
