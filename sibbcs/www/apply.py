"""Public application form. No login.

URL: /apply
"""

import frappe

from sibbcs.admissions.public_form import open_intakes, open_programs

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.programs = open_programs()
	context.intakes = open_intakes()
	context.accepting = bool(context.programs)
	return context
