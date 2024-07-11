#
# Parser for a Spot-like grammar with contexts
#
# Follows the grammar specified in the document
# "Spot’s Temporal Logic Formulas" by Alexandre Duret-Lutz
#

from enum import Enum

from lark import Lark, Token

PARSER = r'''
LIT.2: "true" | "false" | "1" | "0"
ID.1: /[^FGX{extra_ops}\W][\w_]*/ | /"[^"]+"/ | /X\d+/

NEGATION: "!" | "~" | "¬"
DISJUNCTION: "|" | "||" | "\/" | "+" | "∨" | "∪"
CONJUNCTION: "&" | "&&" | "/\\" | "*" | "∧" | "∩"
IMPLICATION: "->" | "=>" | "-->" | "→" | "⟶" | "⇒" | "⟹"
EXCLUSION: "xor" | "^" | "⊕"
EQUIVALENCE: "<->" | "<=>" | "<-->" | "↔" | "⇔"
NEXT: "X" | "()" | "○" | "◯"
EVENTUALLY: "F" | "<>" | "◇" | "⋄" | "♢"
ALWAYS: "G" | "[]" | "□" | "⬜" | "◻"
UNTIL: "U"
WUNTIL: "W"
RELEASE: "R" | "V"
SRELEASE: "M"
FORALL: "A" | "∀"
EXISTS: "E" | "∃"

?start: formula0

?formula0: formula1
    | formula1 IMPLICATION formula0
    | formula1 EQUIVALENCE formula0

?formula1: formula2
    | formula1 EXCLUSION formula2

?formula2: formula3
    | formula2 DISJUNCTION formula3

?formula3: formula4
    | formula3 CONJUNCTION formula4

?formula4: formula5
    | formula5 UNTIL formula4
    | formula5 WUNTIL formula4
    | formula5 RELEASE formula4
    | formula5 SRELEASE formula4

?formula5: formula6
    {extra_unary}
    | EVENTUALLY formula5
    | ALWAYS formula5
    | NEXT formula5
    | NEGATION formula5

?formula6: LIT
    | ID
    | context
    | "(" formula0 ")"

context: ID "[" formula0 "]"

%import common.WS
%ignore WS
'''

CTL_RULES = r'''
    | FORALL formula5
    | EXISTS formula5
'''

# Enumeration of operators
Operator = Enum('Operator', (
	'LIT', 'VAR', 'CTX', 'HOLE',
	'NEGATION', 'DISJUNCTION', 'CONJUNCTION',
	'IMPLICATION', 'EXCLUSION', 'EQUIVALENCE',
	'NEXT', 'EVENTUALLY', 'ALWAYS',
	'UNTIL', 'WUNTIL', 'RELEASE', 'SRELEASE',
	'FORALL', 'EXISTS'
))


class BaseParser:
	"""Base parser for formulae with contexts"""

	def __init__(self, extra_ops='', extra_unary=''):
		self.parser = Lark(PARSER.format(extra_ops=extra_ops, extra_unary=extra_unary), parser='lalr')

	def raw_parse(self, text: str):
		"""Get the raw AST"""
		return self.parser.parse(text)

	def _translate(self, ast):
		"""Translate from Lark to our AST format"""

		# Literal or variable
		if isinstance(ast, Token):
			if ast.type == 'ID':
				return Operator.VAR, ast.value

			elif ast.type == 'LIT':
				return Operator.LIT, ast.value == 'true' or ast.value == '1'

		# Context
		elif ast.data.type == 'RULE' and ast.data.value == 'context':
			args = ast.children
			return Operator.CTX, args[0].value, self._translate(args[1])

		# Temporal or Boolean operator
		else:
			args = ast.children

			if len(args) == 3:
				return Operator[args[1].type], self._translate(args[0]), self._translate(args[2])

			elif len(args) == 2:
				return Operator[args[0].type], self._translate(args[1])

			else:
				raise ValueError('unexpected number of arguments')

	def parse(self, text: str):
		"""Parse a formula with contexts to our internal format"""

		return self._translate(self.parser.parse(text))


class LTLParser(BaseParser):
	"""Spot-like LTL parser with contexts"""

	def __init__(self):
		super().__init__()


class CTLParser(BaseParser):
	"""Spot-like CTL parser with contexts"""

	def __init__(self):
		super().__init__(extra_ops='AE', extra_unary=CTL_RULES)
