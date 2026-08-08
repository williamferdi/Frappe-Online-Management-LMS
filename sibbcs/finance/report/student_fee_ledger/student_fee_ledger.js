frappe.query_reports["Student Fee Ledger"] = {
	filters: [
		{
			fieldname: "student",
			label: __("Student"),
			fieldtype: "Link",
			options: "Student",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "balance" && data && data.balance > 0) {
			value = `<span style="color: var(--text-on-red, #b00)">${value}</span>`;
		}
		return value;
	},
};
