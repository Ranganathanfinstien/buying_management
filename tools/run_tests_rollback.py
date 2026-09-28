"""Run universal_buying test modules against a site WITHOUT persisting anything.

frappe.db.commit is replaced by a no-op and the transaction is rolled back at the end,
so the site keeps no test records. Usage (from the bench's sites folder):

	../env/bin/python ../apps/universal_buying/tools/run_tests_rollback.py buying.local [module_prefix ...]

module_prefix examples: ub_supplier  ub_planning.tests.test_planning_rules
"""

import importlib
import pkgutil
import sys
import traceback
import unittest

import frappe

site = sys.argv[1]
prefixes = sys.argv[2:] or ["ub_supplier", "ub_planning", "ub_sourcing", "ub_ordering", "ub_inward", "ub_finance"]

frappe.init(site=site, sites_path=".")
frappe.connect()
frappe.set_user("Administrator")
frappe.flags.in_test = True
frappe.local.dev_server = True

_real_commit = frappe.db.commit
frappe.db.commit = lambda *a, **k: None
# DDL would commit implicitly; tests must not create custom fields / doctypes.

import universal_buying

names = []
for prefix in prefixes:
	pkg = f"universal_buying.{prefix}"
	if prefix.count(".") >= 2:
		names.append(pkg)
		continue
	tests_pkg = f"universal_buying.{prefix}.tests" if not prefix.endswith("tests") else pkg
	try:
		mod = importlib.import_module(tests_pkg)
	except ModuleNotFoundError:
		continue
	for info in pkgutil.iter_modules(mod.__path__):
		if info.name.startswith("test_"):
			names.append(f"{tests_pkg}.{info.name}")

loader = unittest.TestLoader()
total = unittest.TestResult()
summary = []
for name in names:
	try:
		suite = loader.loadTestsFromName(name)
	except Exception:
		summary.append((name, "IMPORT ERROR", traceback.format_exc(limit=3)))
		continue
	result = unittest.TextTestRunner(verbosity=1, stream=sys.stdout).run(suite)
	frappe.db.rollback()
	summary.append((name, f"run={result.testsRun} fail={len(result.failures)} err={len(result.errors)} skip={len(result.skipped)}", ""))

frappe.db.rollback()
print("\n==== SUMMARY ====")
for name, status, extra in summary:
	print(f"{status:40s} {name}")
	if extra:
		print(extra)
frappe.destroy()
