#
# Equivalence problem for CTL
#

import subprocess

from .common import Op, Problem, instantiate_formula
from .transform import InvalidFormulaError

# Temporal operators
TEMPORAL = frozenset({Op.NEXT, Op.EVENTUALLY, Op.ALWAYS, Op.UNTIL, Op.WUNTIL, Op.RELEASE, Op.SRELEASE})
# Boolean operators
BOOLEAN = frozenset({Op.DISJUNCTION, Op.CONJUNCTION, Op.IMPLICATION, Op.EXCLUSION, Op.EQUIVALENCE})

# ASCII characters reserved by ctl-sat
CTLSAT_RESERVED = {ch for ch in b'^v~->()TAEUFGX$'}

# Map to construct CTL-SAT formulas
CTLSAT_MAP = {
	Op.NEGATION: b'~ %b',
	Op.DISJUNCTION: b'(%b v %b)',
	Op.CONJUNCTION: b'(%s ^ %b)',
	Op.IMPLICATION: b'(%b -> %b)',
	Op.FORALL: b'(A %b)',
	Op.EXISTS: b'(E %s)',
	Op.NEXT: b'X %b',
	Op.EVENTUALLY: b'F %b',
	Op.ALWAYS: b'G %b',
	Op.UNTIL: b'(%b U %b)',
}


def to_ctlsat(ast, var_map):
	"""Translate a formula (without context) to ctl-sat (https://github.com/nicolaprezza/CTLSAT)"""

	head, *args = ast

	match head:
		case Op.LIT:
			# There is only T as a constant for true
			return b'T' if args[0] else b'(~T)'

		case Op.VAR:
			# Variable in CTL-SAT are single ASCII characters, so we need
			# to encode our multicharacter names for atomic propositions
			var_id = var_map.get(args[0])

			if not var_id:
				# The character for the new atomic proposition is the first
				# unused (and not reserved, see below) one
				var_id = next(reversed(var_map.values())) + 1

				# Skip reserved characters (i.e. CTL-SAT operators)
				while var_id in CTLSAT_RESERVED:
					var_id += 1

				# Of course, the number of ASCII characters imposes a limitation
				# on the number of variables, but the complexity of CTL
				# satisfiability imposes a stronger one
				if var_id > 255:
					raise ValueError('too many variables')

				var_map[args[0]] = var_id

			return bytes((var_id,))

		case Op.CTX:
			raise ValueError('cannot convert context to CTL-SAT')

		case Op.HOLE:
			# ! is not negation, just a character for the hole
			# (because it is the first printable character)
			return b'!'

	ctl_args = [to_ctlsat(arg, var_map) for arg in args]
	ctl_head = CTLSAT_MAP.get(head)

	# CTL-SAT does not support some temporal and Boolean operators
	# that need to be converted first to equivalent expressions
	if ctl_head is None:
		raise InvalidFormulaError(f'not a valid CTL formula: {head.name}')

	# Byte string formatting is used to build the formulas
	if len(args) == 1:
		return ctl_head % (ctl_args[0])
	else:
		return ctl_head % (ctl_args[0], ctl_args[1])


def _check_ctl(ast, quant=0):
	"""Check whether a formula is valid CTL"""

	# The meaning of quant is
	# - 0 = state formula expected
	# - 1 = quantifier above (i.e. path formula expected)
	# - 2 = quantifier followed by a negation above (CTL-SAT supports that, but only once)

	head, *args = ast

	match head:
		case Op.LIT | Op.VAR:
			pass

		case Op.CTX:
			# We assume all contexts are state formulae
			if quant != 0:
				raise InvalidFormulaError('context cannot appear as path formula')

			_check_ctl(args[1])

		case Op.NEGATION:
			if quant == 2:
				raise InvalidFormulaError('double negation is not supported')
			elif quant == 1:
				quant = 2

		case Op.FORALL | Op.EXISTS:
			if quant != 0:
				raise InvalidFormulaError('double quantification')

			quant = 1

		case _:
			if head in (TEMPORAL if quant == 0 else BOOLEAN):
				raise InvalidFormulaError(f'unexpected {head.name} operator')

			quant = 0

	all(_check_ctl(arg, quant) for arg in args)


def _adapt_ctl(ast, prev=None, negated=False):
	"""Adapt CTL formula to work with CTL-SAT"""

	head, *args = ast

	# Some special cases
	match head:
		case Op.LIT | Op.VAR:
			return ast

		case Op.CTX:
			return head, args[0], _adapt_ctl(args[1])

		case Op.FORALL | Op.EXISTS:
			return _adapt_ctl(args[0], prev=head)

		case Op.NEGATION if prev is not None:
			return _adapt_ctl(args[0], prev=prev, negated=True)

	# Otherwise, we translate the arguments
	new_args = [_adapt_ctl(arg) for arg in args]

	# Unsupported operators by CTL-SAT, we translate them to the supported ones
	match head:
		case Op.EQUIVALENCE:
			return (Op.CONJUNCTION, (Op.IMPLICATION, new_args[0], new_args[1]),
			        (Op.IMPLICATION, new_args[1], new_args[0]))

		case Op.EXCLUSION:
			return (Op.DISJUNCTION, (Op.CONJUNCTION, new_args[0], (Op.NEGATION, new_args[1])),
			        (Op.CONJUNCTION, new_args[1], (Op.NEGATION, new_args[0])))

		case Op.RELEASE:
			arg = Op.UNTIL, (Op.NEGATION, new_args[0]), (Op.NEGATION, new_args[1])

			if not negated:
				arg = Op.NEGATION, arg

			return prev, arg

		case Op.WUNTIL:
			operand = Op.DISJUNCTION
			until = Op.UNTIL, new_args[0], new_args[1]
			always = Op.ALWAYS, new_args[0]

			if negated:
				operand = Op.CONJUNCTION
				until = Op.NEGATION, until
				always = Op.NEGATION, Op.ALWAYS

			return operand, (prev, until), (prev, always)

		case Op.SRELEASE:
			arg = Op.UNTIL, new_args[1], (Op.CONJUNCTION, new_args[1], new_args[0])

			if negated:
				arg = Op.NEGATION, arg

			return prev, arg

	# Adjust negation
	if head in TEMPORAL:
		arg = head, *new_args
		if negated:
			arg = Op.NEGATION, arg
		return prev, arg

	return head, *new_args


class CTLSpec:
	"""Specification for the CTL transformation"""

	@staticmethod
	def wrap_premise(premise):
		return Op.FORALL, (Op.ALWAYS, premise)


class CTLProblem(Problem):
	"""Equivalence problem for CTL"""

	def __init__(self, left, right, any_formula=False):
		# Check formula
		for f, name in ((left, 'left'), (right, 'right')):
			try:
				_check_ctl(f)
			except InvalidFormulaError as ife:
				# Extend the message with the side of the equation
				raise InvalidFormulaError(f'{name} equation is not valid CTL: {ife}')

		super().__init__(_adapt_ctl(left), _adapt_ctl(right), CTLSpec, any_formula=any_formula)

		# Remove equivalences introduced by the transformation
		if any_formula:
			self.gen_left, self.gen_right, self.gen_cond = \
				map(_adapt_ctl, (self.gen_left, self.gen_right, self.gen_cond))

		# Variable mapping
		self.var_map = {None: 34}  # 34 is ord('!') + 1

	def _solve(self, formula, timeout=None):
		"""Check with ctl-sat"""

		ret = subprocess.run((b'bin/ctl-sat', formula), timeout=timeout, stdout=subprocess.PIPE)

		if ret is None or ret.returncode != 0:
			raise ValueError('error while running ctl-sat')

		# The result is in the penultimate line
		last_line = ret.stdout.split(b'\n')[-2]

		# This is a type in CTL-SAT, so we should reproduce it here
		if b'satisfable' not in last_line:
			raise ValueError('error while running ctl-sat (unexpected output)')

		return b'NOT satisfable' not in last_line

	def _solve_both(self, ctl_lnr, ctl_rnl, timeout=None):
		"""Solve both formulae"""

		rnl = self._solve(ctl_rnl, timeout=timeout)
		lnr = self._solve(ctl_lnr, timeout=timeout)

		equivalent = not rnl and not lnr

		# No model is provided by CTL-SAT as far as we know

		return equivalent, ('no more info' if lnr else None), ('no more info' if rnl else None)

	def solve(self, timeout=60):
		"""Solve with the first method"""

		left = to_ctlsat(self.gen_left, self.var_map)
		right = to_ctlsat(self.gen_right, self.var_map)
		cond = to_ctlsat(self.gen_cond, self.var_map)

		PATTERN = b'(%s) ^ (%s) ^ (~ %s)'

		cnf_lnr = PATTERN % (left, cond, right)
		cnf_rnl = PATTERN % (right, cond, left)

		return self._solve_both(cnf_lnr, cnf_rnl, timeout=timeout)

	def solve_with_context(self, simplify=False, timeout=20):
		"""Obtain witnesses and study their satisfaction"""

		canonical = self.transformer.canonical_context()

		left_inst = instantiate_formula(self.left, canonical)
		right_inst = instantiate_formula(self.right, canonical)

		sat_left = to_ctlsat(_adapt_ctl(left_inst), self.var_map)
		sat_right = to_ctlsat(_adapt_ctl(right_inst), self.var_map)

		pattern = b'%s ^ (~ %s)'

		cnf_lnr = pattern % (sat_left, sat_right)
		cnf_rnl = pattern % (sat_right, sat_left)

		holds, *_ = self._solve_both(cnf_lnr, cnf_rnl, timeout=timeout)

		return canonical, holds

	def canonical_context(self, simplified=False):
		"""Obtain the canonical context"""

		# No simplification for CTL
		return self.transformer.canonical_context()
