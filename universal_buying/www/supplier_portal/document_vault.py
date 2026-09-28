from universal_buying.ub_ordering.portal_pages import prepare

no_cache = 1


def get_context(context):
	suppliers = prepare(context, "document_vault", "Document Vault")
	if not suppliers:
		return
	context.vault = None
	try:
		from universal_buying.ub_supplier.api import get_document_vault
	except ImportError:
		return
	context.vault = get_document_vault(context.current_supplier)
