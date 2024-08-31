#
# Common entry point for all logics
#

from .parser import LTLParser, CTLParser


class ProblemLoader:
	"""Lazy problem loader to avoid requiring uneeded packages"""

	def __init__(self):
		self.cache = {}

	def get(self, key, default=None):
		"""Return the value for key or default otherwise"""

		value = self.cache.get(key)

		if value is None:
			match key:
				case 'ltl':
					from .ltl import LTLProblem
					value = LTLProblem
				case 'ctl':
					from .ctl import CTLProblem
					value = CTLProblem
				case 'bool':
					from .bool import BoolProblem
					value = BoolProblem

			if value is not None:
				self.cache[key] = value

		return value

	def __getitem__(self, key):
		"""Return self[key]"""

		if value := self.get(key):
			return value

		raise KeyError(key)


PROBLEM_CLASS = ProblemLoader()

PARSER_CLASS = {
	'ltl': LTLParser,
	'ctl': CTLParser,
	'bool': LTLParser,
}
