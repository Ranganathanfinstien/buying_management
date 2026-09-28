app_name = "universal_buying"
app_title = "Universal Buying"
app_publisher = "Finstein"
app_description = "Sales Order driven buying with supplier portal, RFQ and inward quality"
app_email = "praveenit2003@gmail.com"
app_license = "mit"

required_apps = ["erpnext"]

after_install = "universal_buying.setup.install.after_install"
after_migrate = ["universal_buying.setup.install.after_migrate"]

# ---------------------------------------------------------------------------
# Hooks are contributed by each module in <module>/hooks_contrib.py.
# Those files must be PURE DATA (no imports) and may define any of:
#   DOC_EVENTS, SCHEDULER_EVENTS, DOCTYPE_JS, DOCTYPE_LIST_JS, OVERRIDE_DOCTYPE_CLASS,
#   OVERRIDE_WHITELISTED_METHODS, PERMISSION_QUERY_CONDITIONS, HAS_PERMISSION,
#   WEBSITE_ROUTE_RULES, STANDARD_PORTAL_MENU_ITEMS, ROLE_HOME_PAGE, JINJA_METHODS,
#   APP_INCLUDE_JS, APP_INCLUDE_CSS, WEB_INCLUDE_JS, WEB_INCLUDE_CSS,
#   UB_ON_SETTINGS_UPDATE, HAS_WEBSITE_PERMISSION, BOOT_SESSION
# Conflicting single-owner keys (OVERRIDE_DOCTYPE_CLASS, DOCTYPE_JS, ...) raise at import.
# ---------------------------------------------------------------------------

_CONTRIB_MODULES = [
	"universal_buying.universal_buying.hooks_contrib",
	"universal_buying.ub_supplier.hooks_contrib",
	"universal_buying.ub_planning.hooks_contrib",
	"universal_buying.ub_sourcing.hooks_contrib",
	"universal_buying.ub_ordering.hooks_contrib",
	"universal_buying.ub_inward.hooks_contrib",
	"universal_buying.ub_finance.hooks_contrib",
]


def _load_contribs():
	import importlib

	out = []
	for name in _CONTRIB_MODULES:
		try:
			out.append((name, importlib.import_module(name)))
		except ModuleNotFoundError as e:
			if e.name != name:
				raise
	return out


def _merge():
	doc_events, scheduler, single = {}, {}, {}
	lists = {k: [] for k in (
		"WEBSITE_ROUTE_RULES", "STANDARD_PORTAL_MENU_ITEMS", "JINJA_METHODS", "APP_INCLUDE_JS", "APP_INCLUDE_CSS",
		"WEB_INCLUDE_JS", "WEB_INCLUDE_CSS", "UB_ON_SETTINGS_UPDATE", "BOOT_SESSION")}
	single_keys = ("DOCTYPE_JS", "DOCTYPE_LIST_JS", "OVERRIDE_DOCTYPE_CLASS", "OVERRIDE_WHITELISTED_METHODS",
		"PERMISSION_QUERY_CONDITIONS", "HAS_PERMISSION", "ROLE_HOME_PAGE", "HAS_WEBSITE_PERMISSION")

	for modname, mod in _load_contribs():
		for dt, events in (getattr(mod, "DOC_EVENTS", {}) or {}).items():
			for ev, handlers in events.items():
				handlers = [handlers] if isinstance(handlers, str) else list(handlers)
				doc_events.setdefault(dt, {}).setdefault(ev, []).extend(handlers)
		for when, jobs in (getattr(mod, "SCHEDULER_EVENTS", {}) or {}).items():
			if when == "cron":
				for expr, fns in jobs.items():
					scheduler.setdefault("cron", {}).setdefault(expr, []).extend(fns)
			else:
				scheduler.setdefault(when, []).extend(jobs)
		for key in single_keys:
			for k, v in (getattr(mod, key, {}) or {}).items():
				bucket = single.setdefault(key, {})
				if k in bucket and bucket[k] != v:
					raise Exception(f"universal_buying hooks: {key}[{k!r}] set twice ({modname})")
				bucket[k] = v
		for key in lists:
			lists[key].extend(getattr(mod, key, []) or [])

	return doc_events, scheduler, single, lists


_doc_events, _scheduler, _single, _lists = _merge()

doc_events = _doc_events
scheduler_events = _scheduler
doctype_js = _single.get("DOCTYPE_JS", {})
doctype_list_js = _single.get("DOCTYPE_LIST_JS", {})
override_doctype_class = _single.get("OVERRIDE_DOCTYPE_CLASS", {})
override_whitelisted_methods = _single.get("OVERRIDE_WHITELISTED_METHODS", {})
permission_query_conditions = _single.get("PERMISSION_QUERY_CONDITIONS", {})
has_permission = _single.get("HAS_PERMISSION", {})
has_website_permission = _single.get("HAS_WEBSITE_PERMISSION", {})
role_home_page = _single.get("ROLE_HOME_PAGE", {})
website_route_rules = _lists["WEBSITE_ROUTE_RULES"]
standard_portal_menu_items = _lists["STANDARD_PORTAL_MENU_ITEMS"]
jinja = {"methods": _lists["JINJA_METHODS"]} if _lists["JINJA_METHODS"] else {}
app_include_js = _lists["APP_INCLUDE_JS"]
app_include_css = _lists["APP_INCLUDE_CSS"]
web_include_js = _lists["WEB_INCLUDE_JS"]
web_include_css = _lists["WEB_INCLUDE_CSS"]
ub_on_settings_update = _lists["UB_ON_SETTINGS_UPDATE"]
boot_session = _lists["BOOT_SESSION"]
