# -*- coding: utf-8 -*-

from odoo import fields, models, api


class AccountingCommonPartnerReport(models.TransientModel):
    _name = 'account.common.partner.report'
    _description = 'Account Common Partner Report'
    _inherit = "account.common.report"
    
    result_selection = fields.Selection([('customer', 'Receivable Accounts'),
                                        ('supplier', 'Payable Accounts'),
                                        ('customer_supplier', 'Receivable and Payable Accounts')
                                      ], string="Partner's Account", required=True, default='customer_supplier')

    def pre_print_report(self, data):
        data['form'].update(self.read(['result_selection'])[0])
        return data

    # @api.onchange('company_id')
    # def _onchange_company_id(self):
    #     if self.company_id:
    #         get_branch = self.env.user.branch_ids.filtered(lambda line: line.company_id.id == self.company_id.id)
    #         return {'domain': {'branch_ids': [('id', 'in', get_branch.ids)]}}
    #
    #     get_branch = self.env['res.branch'].search(
    #         [('id', 'in', self.env.user.branch_ids.ids), ('company_id', '=', self.env.user.company_id.id)])
    #     return {'domain': {'branch_ids': [('id', 'in', get_branch.ids)]}}

