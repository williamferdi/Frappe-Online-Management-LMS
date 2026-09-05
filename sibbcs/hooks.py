app_name = "sibbcs"
app_title = "SIBBCS ERP"
app_publisher = "South India Baptist Bible College & Seminary"
app_description = "Admissions, enrollment, registration, fees, grading and formation for SIBBCS Online"
app_email = "william@sibbc.org"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "sibbcs",
# 		"logo": "/assets/sibbcs/logo.png",
# 		"title": "SIBBCS ERP",
# 		"route": "/sibbcs",
# 		"has_permission": "sibbcs.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/sibbcs/css/sibbcs.css"
# app_include_js = "/assets/sibbcs/js/sibbcs.js"

# include js, css files in header of web template
# web_include_css = "/assets/sibbcs/css/sibbcs.css"
# web_include_js = "/assets/sibbcs/js/sibbcs.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "sibbcs/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "sibbcs/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "sibbcs.utils.jinja_methods",
# 	"filters": "sibbcs.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "sibbcs.install.before_install"
# after_install = "sibbcs.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "sibbcs.uninstall.before_uninstall"
# after_uninstall = "sibbcs.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "sibbcs.utils.before_app_install"
# after_app_install = "sibbcs.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "sibbcs.utils.before_app_uninstall"
# after_app_uninstall = "sibbcs.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "sibbcs.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"sibbcs.tasks.all"
# 	],
# 	"daily": [
# 		"sibbcs.tasks.daily"
# 	],
# 	"hourly": [
# 		"sibbcs.tasks.hourly"
# 	],
# 	"weekly": [
# 		"sibbcs.tasks.weekly"
# 	],
# 	"monthly": [
# 		"sibbcs.tasks.monthly"
# 	],
# }

# Testing
# -------

before_tests = "sibbcs.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "sibbcs.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "sibbcs.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["sibbcs.utils.before_request"]
# after_request = ["sibbcs.utils.after_request"]

# Job Events
# ----------
# before_job = ["sibbcs.utils.before_job"]
# after_job = ["sibbcs.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"sibbcs.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


# ---------------------------------------------------------------------------
# SIBBCS
# ---------------------------------------------------------------------------

scheduler_events = {
	"hourly": [
		# Registered-but-not-in-LMS is exactly the state a student reports as
		# "I can't see my course", so retry it rather than wait for a ticket.
		"sibbcs.academic.lms_sync.sync_pending",
	],
}

doc_events = {
	"LMS Quiz Submission": {
		# A mark entered in the entrance exam course reaches the admissions
		# record on the same save. Before this it stayed in the LMS and the
		# application went on saying the score was zero.
		"after_insert": "sibbcs.admissions.entrance_exam.on_quiz_submission",
		"on_update": "sibbcs.admissions.entrance_exam.on_quiz_submission",
	},
	"Course Registration": {
		"on_update": "sibbcs.finance.hooks_handlers.course_registration_on_update",
	},
	"Fee Invoice": {
		"on_update": "sibbcs.finance.hooks_handlers.open_course_when_fee_settled",
	},
}

scheduler_events["daily"] = [
	# Bills only on the day a term actually starts; per-term idempotent.
	"sibbcs.finance.fees.run_term_tuition_scheduled",
	"sibbcs.finance.hooks_handlers.sweep_missing_registration_fees",
]

# --- the React front end ------------------------------------------------
# Every /portal and /console address is one page; React Router decides what
# to render. Without the <path:app_path> rules a refresh on a deep link asks
# Frappe for a page it has never heard of and gets a 404.
# Not /console: Werkzeug's debug middleware reserves that exact path for its
# interactive console (`console_path="/console"`), and `bench start` wraps the
# app in it -- so /console answered 400 before Frappe ever saw the request,
# while /console/anything worked. The name would come back once the site runs
# under gunicorn, which is precisely the kind of difference between
# development and production not worth carrying.
# Every website page gets the built assets version, so a change to the guest
# stylesheet reaches somebody who has been here before.
update_website_context = "sibbcs.setup.website.add_asset_version"

# The app shell names a hashed bundle and carries a CSRF token; a browser
# that keeps it keeps running the previous build.
after_request = ["sibbcs.setup.website.no_store_on_app_shell"]

website_route_rules = [
	{"from_route": "/portal/<path:app_path>", "to_route": "_portal"},
	{"from_route": "/portal", "to_route": "_portal"},
	{"from_route": "/staff/<path:app_path>", "to_route": "_portal"},
	{"from_route": "/staff", "to_route": "_portal"},
]


# --- who may see whose marks --------------------------------------------
# The permission matrix says what a role may do with a DocType; it cannot say
# which rows. Both halves are needed: the query condition filters a list, and
# has_permission guards the same record fetched by name. The /staff API reads
# through frappe.get_all and is subject to neither -- it calls
# permissions.assert_may_teach for itself.
permission_query_conditions = {
	"Course Registration": "sibbcs.academic.permissions.course_registration_query",
	"Course Assignment": "sibbcs.academic.permissions.course_assignment_query",
	"Assignment Submission": "sibbcs.academic.permissions.assignment_submission_query",
	"Course Grade Scheme": "sibbcs.academic.permissions.course_grade_scheme_query",
	"Student": "sibbcs.academic.permissions.student_query",
	"Program Enrollment": "sibbcs.academic.permissions.program_enrollment_query",
}

has_permission = {
	"Course Registration": "sibbcs.academic.permissions.course_registration_permission",
	"Course Assignment": "sibbcs.academic.permissions.course_assignment_permission",
	"Assignment Submission": "sibbcs.academic.permissions.assignment_submission_permission",
	"Course Grade Scheme": "sibbcs.academic.permissions.course_grade_scheme_permission",
	"Student": "sibbcs.academic.permissions.student_permission",
	"Program Enrollment": "sibbcs.academic.permissions.program_enrollment_permission",
}
