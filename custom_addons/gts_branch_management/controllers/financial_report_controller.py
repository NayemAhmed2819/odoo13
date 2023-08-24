# # -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import webbrowser
from odoo import api, fields, models, _


class ReportFinancialWithPartner(http.Controller):
    @http.route(['/financial_report/<string:account_name>/<int:company_id>/<string:date_start>/<string:date_end>'],
                website=True,
                auth='public')
    def get_financial_report(self, applicant_id=None, account_name=None, company_id=None, date_start=None,
                             date_end=None, **kwargs):
        print(applicant_id)
        print(account_name)
        print(company_id)
        print(date_start)
        date_start_fn = False
        if date_start != "No date":
            date_start_fn = date_start
        print(date_start_fn)
        date_end_fn = False
        if date_end != "No date":
            date_end_fn = date_end
        print(date_end_fn)

        name_data = ''.join([i for i in account_name if not i.isdigit()]).lstrip()
        print(name_data)

        account_id = request.env['account.account'].sudo().search(
            [('name', '=', name_data), ('company_id', '=', company_id)])

        company_data = request.env['res.company'].search([('id','=',company_id)])
        journal_ids = request.env['account.journal'].search([('company_id','=',company_data.id)])

        records = None
        data = {'active_ids':138,'active_model':'account.report.general.ledger','ids': [], 'model': 'ir.ui.menu', 'form': {'id': 136, 'date_from': date_start_fn, 'date_to': date_end_fn,
                                                           'journal_ids': journal_ids.ids, 'target_move': 'posted',
                                                           'company_id': (company_data.id, company_data.name),
                                                           'branch_ids': {'id': 136, 'branch_ids': False},
                                                           'used_context': {'branch_ids': '',
                                                                            'journal_ids': journal_ids.ids, 'state': 'posted',
                                                                            'date_from': date_start_fn, 'date_to': date_end_fn,
                                                                            'strict_range': False, 'lang': 'en_US'},
                                                           'display_account': 'movement', 'initial_balance': False,
                                                           'sortby': 'sort_date',
                                                           'coa_ids': (account_id.id, account_id.code + " " + account_id.name)}}
        # return request.env.ref('gts_financial_pdf_report.action_report_general_ledger').with_context(
        #     landscape=True).report_action(records, data=data)

        r = request.env['report.gts_financial_pdf_report.report_generalledger']

        pdf, _ = request.env.ref('gts_financial_pdf_report.action_report_general_ledger').with_context(landscape=True).render_qweb_pdf(r,data=data)
        pdfhttpheaders = [('Content-Type', 'application/pdf'), ('Content-Length', len(pdf))]
        print(pdfhttpheaders)


        return request.make_response(pdf, headers=pdfhttpheaders)
