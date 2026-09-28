# Copyright (c) 2026, Finstein and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SupplierDocument(Document):
	# status / uploaded_on are maintained by universal_buying.ub_supplier.api.sync_vault_rows (Supplier.validate)
	pass
