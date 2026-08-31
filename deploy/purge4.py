import sys
import frappe

APPLY = "apply" in sys.argv
frappe.init(site="online.sibbc.org"); frappe.connect(); frappe.set_user("Administrator")
frappe.flags.in_migrate = True

print("workflow actions left over from the test applications:")
for row in frappe.get_all("Workflow Action",
                          fields=["name", "reference_doctype", "reference_name"],
                          limit_page_length=0):
	print(f"   {row.name} -> {row.reference_doctype} {row.reference_name}")
	if APPLY:
		frappe.delete_doc("Workflow Action", row.name, ignore_permissions=True,
		                  delete_permanently=True, ignore_missing=True, force=True)

# Scholarship Request <-> Admission Application is the last two-document cycle.
print("\ncutting the scholarship cycle:")
for row in frappe.get_all("Scholarship Request", fields=["name", "application"], limit_page_length=0):
	print(f"   Scholarship Request {row.name}.application = {row.application} -> null")
	if APPLY:
		frappe.db.set_value("Scholarship Request", row.name, "application", None,
		                    update_modified=False)
if APPLY:
	frappe.db.commit()

KEEP_USERS = {"Administrator", "Guest", "ramsemz@sibbc.org"}
ORDER = ["Admission Application", "Scholarship Request", "Student"]

print()
total = 0
for attempt in range(1, 6):
	progress, blocked = 0, []
	targets = [(dt, n) for dt in ORDER for n in frappe.get_all(dt, pluck="name")]
	targets += [("User", n) for n in frappe.get_all("User", pluck="name") if n not in KEEP_USERS]
	for dt, name in targets:
		if not frappe.db.exists(dt, name):
			continue
		if not APPLY:
			blocked.append((dt, name, "dry run")); continue
		try:
			frappe.delete_doc(dt, name, ignore_permissions=True, delete_permanently=True,
			                  ignore_missing=True)
			frappe.db.commit(); progress += 1; total += 1
		except Exception as e:
			frappe.db.rollback()
			blocked.append((dt, name, frappe.utils.strip_html(str(e)).replace("\n", " ")[:150]))
	print(f"pass {attempt}: removed {progress}, blocked {len(blocked)}")
	if not progress:
		for dt, name, err in blocked:
			print(f"   BLOCKED {dt} {name}: {err}")
		break
print(f"\ntotal removed: {total}")
