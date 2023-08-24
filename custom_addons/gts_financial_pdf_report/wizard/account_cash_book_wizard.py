# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2019-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
from datetime import date, datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DATETIME_FORMAT, BytesIO, xlsxwriter, base64
from odoo import fields, models
# from custom_addons.accounting_report.models.usl_xlxs_report_tools import UslXlxsReportUtil as utill


class CashBookWizard(models.TransientModel):
    _inherit = "account.common.account.report"
    _name = 'account.cash.book.report'
    _description = 'Account Cash Book Report'

    company_id = fields.Many2one('res.company', string='Company', domain=lambda self: self._get_companies(),
                                 default=lambda self: self.env.user.company_id, required=True)
    target_move = fields.Selection([('posted', 'All Posted Entries'),
                                    ('all', 'All Entries')], string='Target Moves', required=True,
                                   default='posted')
    date_from = fields.Date(string='Start Date', default=date.today(),
                            requred=True)
    date_to = fields.Date(string='End Date', default=date.today(),
                          requred=True)
    display_account = fields.Selection(
        [('all', 'All'), ('movement', 'With movements'),
         ('not_zero', 'With balance is not equal to 0')],
        string='Display Accounts', required=True, default='movement')
    sortby = fields.Selection(
        [('sort_date', 'Date'), ('sort_journal_partner', 'Journal & Partner')],
        string='Sort by',
        required=True, default='sort_date')
    initial_balance = fields.Boolean(string='Include Initial Balances',
                                     help='If you selected date, this field allow you to add a row to display the amount of debit/credit/balance that precedes the filter you\'ve set.', default=True)

    def _get_companies(self):
        query = """select * from res_company_users_rel where user_id={}""".format(self.env.user.id)
        self._cr.execute(query=query)
        allowed_companies = self._cr.fetchall()
        allowed_company = []
        for company in allowed_companies:
            allowed_company.append(company[0])
        return [('id', 'in', allowed_company)]

    def _get_default_account_ids(self):
        journals = self.env['account.journal'].search([('type', '=', 'cash')])
        accounts = []
        for journal in journals:
            accounts.append(journal.default_credit_account_id.id)
        return accounts

    account_ids = fields.Many2many('account.account',
                                   'account_report_cashbook_account_rel',
                                   'report_id', 'account_id',
                                   'Accounts',
                                   default=_get_default_account_ids)
    journal_ids = fields.Many2many('account.journal',
                                   'account_report_cashbook_journal_rel',
                                   'account_id', 'journal_id',
                                   string='Journals', required=True,
                                   default=lambda self: self.env[
                                       'account.journal'].search([]))

    branch_ids = fields.Many2one('res.branch', string='Branch')
    datas = fields.Binary('File', readonly=True)
    datas_fname = fields.Char('Filename', readonly=True)

    def _get_account_move_entry(self, accounts, init_balance, sortby,
                                display_account):

        cr = self.env.cr
        move_line = self.env['account.move.line']
        move_lines = {x: [] for x in accounts.ids}

        # Prepare initial sql query and Get the initial move lines
        if init_balance:
            init_tables, init_where_clause, init_where_params = move_line.with_context(
                date_from=self.env.context.get('date_from'), date_to=False,
                initial_bal=True)._query_get()
            init_wheres = [""]
            if init_where_clause.strip():
                init_wheres.append(init_where_clause.strip())
            init_filters = " AND ".join(init_wheres)
            filters = init_filters.replace('account_move_line__move_id',
                                           'm').replace('account_move_line',
                                                        'l')
            sql = ("""SELECT 0 AS lid, l.account_id AS account_id, '' AS ldate, '' AS lcode, 0.0 AS amount_currency, '' AS lref, 'Initial Balance' AS lname, COALESCE(SUM(l.debit),0.0) AS debit, COALESCE(SUM(l.credit),0.0) AS credit, COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit), 0) as balance, '' AS lpartner_id,\
                    '' AS move_name, '' AS mmove_id, '' AS currency_code,\
                    NULL AS currency_id,\
                    '' AS invoice_id, '' AS invoice_type, '' AS invoice_number,\
                    '' AS partner_name, '' as branch_name\
                    FROM account_move_line l\
                    LEFT JOIN account_move m ON (l.move_id=m.id)\
                    LEFT JOIN res_currency c ON (l.currency_id=c.id)\
                    LEFT JOIN res_partner p ON (l.partner_id=p.id)\
                    JOIN account_journal j ON (l.journal_id=j.id)\
                    WHERE l.account_id IN %s""" + filters + ' GROUP BY l.account_id')
            params = (tuple(accounts.ids),) + tuple(init_where_params)
            cr.execute(sql, params)
            for row in cr.dictfetchall():
                move_lines[row.pop('account_id')].append(row)
        sql_sort = 'l.date, l.move_id'
        if sortby == 'sort_journal_partner':
            sql_sort = 'j.code, p.name, l.move_id'

        # Prepare sql query base on selected parameters from wizard
        tables, where_clause, where_params = move_line._query_get()
        wheres = [""]
        if where_clause.strip():
            wheres.append(where_clause.strip())
        filters = " AND ".join(wheres)
        filters = filters.replace('account_move_line__move_id', 'm').replace(
            'account_move_line', 'l')

        # Get move lines base on sql query and Calculate the total balance of move lines
        sql = ('''SELECT l.id AS lid, l.account_id AS account_id, to_char(l.date, 'dd/mm/yyyy') AS ldate, j.code AS lcode, l.currency_id, l.amount_currency, l.ref AS lref, l.name AS lname, COALESCE(l.debit,0) AS debit, COALESCE(l.credit,0) AS credit, COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit), 0) AS balance,\
                m.name AS move_name, c.symbol AS currency_code, p.name AS partner_name, rb.name as branch_name\
                FROM account_move_line l\
                JOIN account_move m ON (l.move_id=m.id)\
                LEFT JOIN res_currency c ON (l.currency_id=c.id)\
                LEFT JOIN res_partner p ON (l.partner_id=p.id)\
                LEFT JOIN res_branch rb ON (m.branch_id=rb.id)\
                JOIN account_journal j ON (l.journal_id=j.id)\
                JOIN account_account acc ON (l.account_id = acc.id) \
                WHERE l.account_id IN %s ''' + filters + ''' and m.state != 'cancel' GROUP BY rb.name, l.id, l.account_id, l.date, j.code, l.currency_id, l.amount_currency, l.ref, 
                l.name, m.name, c.symbol, p.name ORDER BY rb.name, ''' + sql_sort)
        params = (tuple(accounts.ids),) + tuple(where_params)
        cr.execute(sql, params)

        for row in cr.dictfetchall():
            balance = 0
            for line in move_lines.get(row['account_id']):
                balance += line['debit'] - line['credit']
            row['balance'] += balance
            move_lines[row.pop('account_id')].append(row)

        # Calculate the debit, credit and balance for Accounts
        account_res = []
        for account in accounts:
            currency = account.currency_id and account.currency_id or account.company_id.currency_id
            res = dict((fn, 0.0) for fn in ['credit', 'debit', 'balance'])
            res['code'] = account.code
            res['name'] = account.name
            res['move_lines'] = move_lines[account.id]
            for line in res.get('move_lines'):
                res['debit'] += line['debit']
                res['credit'] += line['credit']
                res['balance'] = line['balance']
            if display_account == 'all':
                account_res.append(res)
            if display_account == 'movement' and res.get('move_lines'):
                account_res.append(res)
            if display_account == 'not_zero' and not currency.is_zero(
                    res['balance']):
                account_res.append(res)

        return account_res

    @api.onchange('account_ids')
    def onchange_account_ids(self):
        if self.account_ids:
            journals = self.env['account.journal'].search(
                [('type', '=', 'cash')])
            accounts = []
            for journal in journals:
                accounts.append(journal.default_credit_account_id.id)
            domain = {'account_ids': [('id', 'in', accounts)]}
            return {'domain': domain}

    def _build_contexts(self, data):
        result = {}
        result['journal_ids'] = 'journal_ids' in data['form'] and data['form'][
            'journal_ids'] or False
        result['state'] = 'target_move' in data['form'] and data['form'][
            'target_move'] or ''
        result['date_from'] = data['form']['date_from'] or False
        result['date_to'] = data['form']['date_to'] or False
        result['strict_range'] = True if result['date_from'] else False
        if data['form']['branch_ids']:
            result['branch_ids'] = 'branch_ids' in data['form'] and data['form']['branch_ids'][0] or False
        result['company_id'] = data['form']['company_id'][0]
        return result

    def check_report(self):
        self.ensure_one()
        if self.initial_balance and not self.date_from:
            raise UserError(_("You must choose a Start Date"))
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(
            ['date_from', 'date_to', 'journal_ids', 'target_move',
             'display_account',
             'account_ids', 'sortby', 'initial_balance', 'branch_ids', 'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = dict(used_context,
                                            lang=self.env.context.get(
                                                'lang') or 'en_US')
        return self.env.ref('gts_financial_pdf_report.action_report_cash_book').report_action(self, data=data)

    def check_excel_report(self):
        print('check_excel_report')
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(
            ['date_from', 'date_to', 'journal_ids', 'target_move',
             'display_account',
             'account_ids', 'sortby', 'initial_balance', 'branch_ids', 'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = dict(used_context,
                                            lang=self.env.context.get(
                                                'lang') or 'en_US')

        # self.model = self.env.context.get('active_model')
        # docs = self.env[self.model].browse(
        #     self.env.context.get('active_ids', []))
        init_balance = data['form'].get('initial_balance', True)
        sortby = data['form'].get('sortby', 'sort_date')
        display_account = 'movement'
        codes = []
        if data['form'].get('journal_ids', False):
            codes = [journal.code for journal in
                     self.env['account.journal'].search(
                         [('id', 'in', data['form']['journal_ids'])])]
        account_ids = data['form']['account_ids']
        accounts = self.env['account.account'].search(
            [('id', 'in', account_ids)])
        accounts_res = self.with_context(
            data['form'].get('used_context', {}))._get_account_move_entry(
            accounts,
            init_balance,
            sortby,
            display_account)
        dt = {
            'data': data['form'],

            'Accounts': accounts_res,
            'print_journal': codes,
        }
        report_name = self.env.user.company_id.name + " : " + 'Cash Book Report'
        print(report_name)
        filename = '%s : %s' % (self.env.user.company_id.name, report_name)
        fp = BytesIO()
        workbook = xlsxwriter.Workbook(fp)
        wbf, workbook = utill.add_workbook_format(workbook=workbook)

        worksheet = workbook.add_worksheet(report_name)
        worksheet.merge_range('A2:I3', report_name, wbf['title_doc'])
        datas = dt['data']
        datas['date_from'] = datas['date_from'].strftime('%d/%m/%Y')
        datas['date_to'] = datas['date_to'].strftime('%d/%m/%Y')
        worksheet.merge_range('A4:I4', "Date : " + str(datas['date_from']) + " : " + str(datas['date_to']),
                              wbf['title_doc'])
        print_journal = dt['print_journal']
        print_jurnals = ', '.join([lt or '' for lt in print_journal])
        worksheet.merge_range('A6:C6', "Journals : ",
                              wbf['header_detail'])
        worksheet.merge_range('A7:C7', print_jurnals,
                              wbf['header_detail'])
        worksheet.merge_range('E6:F6', 'Display Account', wbf['header_detail'])
        display_account = None
        if datas['display_account'] == 'all':
            display_account = 'All accounts'
        elif datas['display_account'] == 'movement':
            display_account = 'With movements'
        elif datas['display_account'] == 'not_zero':
            display_account = 'With balance not equal to zero'

        worksheet.merge_range('E7:F7', display_account,
                              wbf['header_detail'])

        worksheet.merge_range('H6:I6', "Target Moves",
                        wbf['header_detail'])
        target_move = None
        if datas['target_move'] == 'all':
            target_move = 'All Entries'
        elif datas['target_move'] == 'posted':
            target_move = 'All Posted Entries'

        worksheet.merge_range('H7:I7', target_move,
                              wbf['header_detail'])

        row = 10
        column_name = [
            ('Date', 15, 'char'),
            ('JRNL', 20, 'char'),
            ('Partner', 20, 'char'),
            ('Ref', 20, 'char'),
            ('Move', 20, 'char'),
            ('Entry Label', 20, 'char'),
            ('Debit', 20, 'char'),
            ('Credit', 20, 'char'),
            ('Balance', 20, 'char'),
            ('Currency', 20, 'char'),
            ('Branch', 20, 'char'),
        ]
        col = 0
        for column in column_name:
            column_name = column[0]
            column_width = column[1]
            worksheet.set_column(col, col, column_width)
            worksheet.write(row, col, column_name, wbf['header_orange'])
            col += 1
        row += 1
        accounts = dt['Accounts']
        for account in accounts:
            col = 0
            worksheet.write(row, col, str(account['code']))
            col += 1
            worksheet.write(row, col, account['name'])
            col += 5
            worksheet.write(row, col, account['debit'])
            col += 1
            worksheet.write(row, col, account['credit'])
            col += 1
            worksheet.write(row, col, account['balance'])
            col += 1
            # worksheet.write(row, col, account['balance'])
            col += 1
            row += 1

            for line in account['move_lines']:
                col = 0
                worksheet.write(row, col, str(line['ldate']))
                col += 1
                worksheet.write(row, col, line['lcode'])
                col += 1
                worksheet.write(row, col, line['partner_name'])
                col += 1
                worksheet.write(row, col, line['lref'])
                col += 1
                worksheet.write(row, col, line['move_name'])
                col += 1
                worksheet.write(row, col, line['lname'])
                col += 1
                worksheet.write(row, col, line['debit'])
                col += 1
                worksheet.write(row, col, line['credit'])
                col += 1
                worksheet.write(row, col, line['balance'])
                col += 1
                # worksheet.write(row, col, line['amount_currency'])
                col += 1
                worksheet.write(row, col, line['branch_name'])
                col += 1
                row += 1

        workbook.close()
        out = base64.encodestring(fp.getvalue())
        self.write({'datas': out, 'datas_fname': filename})
        fp.close()
        filename += '%2Exlsx'

        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': 'web/content/?model=' + self._name + '&id=' + str(
                self.id) + '&field=datas&download=true&filename=' + filename,
        }
