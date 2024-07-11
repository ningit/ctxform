#
# Service for a web-based interface
#

import json
from subprocess import TimeoutExpired

import tornado.escape
import tornado.ioloop
import tornado.web
from lark.exceptions import LarkError
from tornado.httpserver import HTTPServer
from tornado.netutil import bind_unix_socket

from .logics import PROBLEM_CLASS, PARSER_CLASS
from .ltl import to_spot
from .printer import pretty_print, html_colorizer, mathml_print
from .transform import InvalidFormulaError


class MainHandler(tornado.web.RequestHandler):
	"""Handler of equivalence checking requests"""

	def _parse_formula(self, logic, text, side):
		"""Parse a formula or show an error"""

		try:
			# The parsers are kept in the application
			parser = self.application.ctl_parser if logic == 'ctl' else self.application.ltl_parser
			formula = parser.parse(text)
			return formula
		except LarkError:
			self.write({'ok': False, 'reason': f'cannot parse {side} formula'})

		return None

	def post(self):
		"""Answer to an equivalence check request"""

		if self.request.headers.get('Content-Type') != 'application/json':
			self.send_error(400)
		else:
			try:
				data = tornado.escape.json_decode(self.request.body)

				left = data.get('left')
				right = data.get('right')
				logic = data.get('logic', 'ltl')

				# Missing parameters
				if left is None or right is None:
					self.write({'ok': False, 'reason': 'missing parameters'})
					return

				# Try to parse formulae
				if (parsed_left := self._parse_formula(logic, left, 'left')) is None:
					return

				if (parsed_right := self._parse_formula(logic, right, 'right')) is None:
					return

				# Whether to consider any formula or only monotonic ones
				any_formula = not data.get('monotonic', True)

				try:
					problem_type = PROBLEM_CLASS.get(logic)

					if problem_type is None:
						self.write({'ok': False, 'reason': f'unknown logic: {logic}'})
						return

					problem = problem_type(parsed_left, parsed_right, any_formula=any_formula)
					equiv, lword, rword = problem.solve()

				except InvalidFormulaError as ife:
					self.write({'ok': False, 'reason': str(ife)})
					return

				except TimeoutExpired:
					self.write({'ok': False, 'reason': 'timed-out'})
					return

				# Simplified and unsimplified witness
				witnesses = problem.canonical_context(simplified=True)
				unsimplified = problem.canonical_context(simplified=False)

				# We do not support separate witnesses for each implication in the web interface
				if isinstance(witnesses, tuple):
					witnesses = unsimplified

				not_ltl = logic != 'ltl'

				base_response = {
					'ok': True,
					'equivalent': equiv,
					'lword': str(lword) if lword else None,
					'rword': str(rword) if rword else None,
					'witnesses': {ctx_var: {
						'raw': pretty_print(repl, color=html_colorizer),
						'unsimp': pretty_print(unsimp, color=html_colorizer),
						'spot': str(to_spot(repl).simplify()) if logic != 'ctl' else None,
						'math': mathml_print(repl),
					}
						for (ctx_var, repl), unsimp in zip(witnesses.items(), unsimplified.values())},
					'lformula': pretty_print(problem.gen_left, color=html_colorizer),
					'rformula': pretty_print(problem.gen_right, color=html_colorizer),
					'cformula': pretty_print(problem.gen_cond, color=html_colorizer),
				}

				# Specific for LTL
				self.write(base_response | {
					'lformula_spot': None if not_ltl else str(problem.spot_left),
					'rformula_spot': None if not_ltl else str(problem.spot_right),
					'cformula_spot': None if not_ltl else str(problem.spot_cond),
					'rsize': None if not_ltl else problem.aut_right.num_states(),
					'nrsize': None if not_ltl else problem.aut_not_right.num_states(),
					'lsize': None if not_ltl else problem.aut_left.num_states(),
					'nlsize': None if not_ltl else problem.aut_not_left.num_states(),
					'csize': None if not_ltl else problem.aut_cond.num_states(),
				})

			except json.decoder.JSONDecodeError:
				self.send_error(400)


def main():
	import argparse

	arg_parser = argparse.ArgumentParser(description='Equivalence checking as a service')
	arg_parser.add_argument('path', help='Unix socket path or port in standalone mode')
	arg_parser.add_argument('--standalone', '-s', help='Run in standalone mode', action='store_true')

	args = arg_parser.parse_args()

	if args.standalone:
		paths = (
			(r'/api', MainHandler),
			(r'/(.*)', tornado.web.StaticFileHandler, {'path': 'web', 'default_filename': 'index.htm'}),
		)
	else:
		paths = (
			(r'/.*', MainHandler),
		)

	app = tornado.web.Application(paths)
	server = HTTPServer(app)

	# Lark parsers are reentrant?
	app.ltl_parser = PARSER_CLASS['ltl']()
	app.ctl_parser = PARSER_CLASS['ctl']()

	if args.standalone:
		server.listen(int(args.path))
	else:
		socket = bind_unix_socket(args.path)
		server.add_socket(socket)

	tornado.ioloop.IOLoop.instance().start()


if __name__ == '__main__':
	main()
