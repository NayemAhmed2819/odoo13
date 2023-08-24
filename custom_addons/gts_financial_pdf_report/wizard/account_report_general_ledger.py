# -*- coding: utf-8 -*-

from odoo import fields, models, _, api
from odoo.exceptions import UserError
import time
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DATE_FORMAT
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DATETIME_FORMAT, datetime, relativedelta, BytesIO, xlsxwriter, \
    base64
# from custom_addons.accounting_report.models.usl_xlxs_report_tools import UslXlxsReportUtil as utill


class AccountReportGeneralLedger(models.TransientModel):
    _inherit = "account.common.account.report"
    _name = "account.report.general.ledger"
    _description = "General Ledger Report"

    initial_balance = fields.Boolean(string='Include Initial Balances',
                                     help='If you selected date, this field allow you to add a row to display the amount of debit/credit/balance that precedes the filter you\'ve set.', default=True)
    sortby = fields.Selection([('sort_date', 'Date'), ('sort_journal_partner', 'Journal & Partner')], string='Sort by',
                              required=True, default='sort_date')
    journal_ids = fields.Many2many('account.journal', 'account_report_general_ledger_journal_rel', 'account_id',
                                   'journal_id', string='Journals', required=True)
    coa_ids = fields.Many2one('account.account', string='Account Head',
                              index=True, ondelete="restrict", check_company=True, required=True,
                              domain=[('deprecated', '=', False)])

    def _get_account_move_entry(self, accounts, init_balance, sortby, display_account, coa_ids, company_id, date_from):
        print(company_id)
        """
        :param:
                accounts: the recordset of accounts
                init_balance: boolean value of initial_balance
                sortby: sorting by date or partner and journal
                display_account: type of account(receivable, payable and both)

        Returns a dictionary of accounts with following key and value {
                'code': account code,
                'name': account name,
                'debit': sum of total debit amount,
                'credit': sum of total credit amount,
                'balance': total balance,
                'amount_currency': sum of amount_currency,
                'move_lines': list of move line
        }
        """
        cr = self.env.cr
        MoveLine = self.env['account.move.line']
        move_lines = {x: [] for x in accounts.ids}
        acc_id = coa_ids[0]

        # Prepare initial sql query and Get the initial move lines
        if init_balance and date_from:
            init_tables, init_where_clause, init_where_params = MoveLine.with_context(
                date_from=self.env.context.get('date_from'), date_to=False, initial_bal=True)._query_get()
            init_wheres = [""]
            if init_where_clause.strip():
                init_wheres.append(init_where_clause.strip())
            init_filters = " AND ".join(init_wheres)
            filters = init_filters.replace('account_move_line__move_id', 'm').replace('account_move_line', 'l')
            # sql = ("""SELECT 0 AS lid, l.account_id AS account_id, '' AS ldate, '' AS lcode, NULL AS amount_currency, '' AS lref, 'Initial Balance' AS lname, COALESCE(SUM(l.debit),0.0) AS debit, COALESCE(SUM(l.credit),0.0) AS credit, COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit), 0) as balance, '' AS lpartner_id,\
            #     '' AS move_name, '' AS mmove_id, '' AS currency_code,\
            #     NULL AS currency_id,\
            #     '' AS invoice_id, '' AS invoice_type, '' AS invoice_number,\
            #     '' AS partner_name\
            #     FROM account_move_line l\
            #     LEFT JOIN account_move m ON (l.move_id=m.id)\
            #     LEFT JOIN res_currency c ON (l.currency_id=c.id)\
            #     LEFT JOIN res_partner p ON (l.partner_id=p.id)\
            #     JOIN account_journal j ON (l.journal_id=j.id)\
            #     JOIN account_account acc ON (l.account_id = acc.id)\
            #     WHERE l.account_id = %s""" + filters + ' GROUP BY l.account_id')
            # params = (tuple(accounts.ids),) + tuple(init_where_params)

            sql = ("""SELECT 0 AS lid, l.account_id AS account_id, '' AS ldate, '' AS lcode, 0.0 AS amount_currency, '' AS lref, 'Initial Balance' AS lname, COALESCE(SUM(l.debit),0.0) AS debit, COALESCE(SUM(l.credit),0.0) AS credit, COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit), 0) as balance, '' AS lpartner_id,\
                            '' AS move_name, '' AS mmove_id, '' AS currency_code,\
                            NULL AS currency_id,\
                            '' AS invoice_id, '' AS invoice_type, '' AS invoice_number,\
                            '' AS partner_name, '' AS cheque_no, '' AS description, '' AS create_by\
                            FROM account_move_line l\
                            LEFT JOIN account_move m ON (l.move_id=m.id)\
                            LEFT JOIN res_currency c ON (l.currency_id=c.id)\
                            LEFT JOIN res_partner p ON (l.partner_id=p.id)\
                            LEFT JOIN account_move i ON (m.id =i.id)\
                            JOIN account_journal j ON (l.journal_id=j.id)\
                            WHERE m.state != 'cancel' and m.company_id= %s and l.account_id = %s""" + filters + '  GROUP BY l.account_id')

            params = (company_id[0], acc_id,) + tuple(init_where_params)
            cr.execute(sql, params)
            for row in cr.dictfetchall():
                move_lines[row.pop('account_id')].append(row)

        sql_sort = 'l.date, l.move_id'
        if sortby == 'sort_journal_partner':
            sql_sort = 'j.code, p.name, l.move_id'

        # Prepare sql query base on selected parameters from wizard
        tables, where_clause, where_params = MoveLine._query_get()
        wheres = [""]
        if where_clause.strip():
            wheres.append(where_clause.strip())
        filters = " AND ".join(wheres)
        filters = filters.replace('account_move_line__move_id', 'm').replace('account_move_line', 'l')

        # Get move lines base on sql query and Calculate the total balance of move lines
        sql = ('''SELECT l.id AS lid, l.account_id AS account_id, to_char(l.date, 'dd/mm/yyyy') AS ldate, j.code AS lcode, l.currency_id, l.amount_currency, l.ref AS lref, l.name AS lname, COALESCE(l.debit,0) AS debit, COALESCE(l.credit,0) AS credit, COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit), 0) AS balance,\
            m.name AS move_name, c.symbol AS currency_code, p.name AS partner_name, COALESCE(ap.cheque_reference, '') as cheque_no, COALESCE(ap.communication, '') as description, rup.name as create_by\
            FROM account_move_line l\
            JOIN account_move m ON (l.move_id=m.id)\
            LEFT JOIN res_currency c ON (l.currency_id=c.id)\
            LEFT JOIN res_partner p ON (l.partner_id=p.id)\
            JOIN account_journal j ON (l.journal_id=j.id)\
            JOIN account_account acc ON (l.account_id = acc.id) \
            LEFT JOIN account_payment ap on ap.id = l.payment_id
            LEFT JOIN res_users as ru on ru.id = m.create_uid
            LEFT JOIN res_partner as rup on rup.id = ru.partner_id
            WHERE m.company_id=%s and m.state != 'cancel' and l.account_id = %s ''' + filters + ''' GROUP BY l.id, l.account_id, l.date, j.code, l.currency_id, l.amount_currency, l.ref, l.name, m.name, c.symbol, p.name, ap.cheque_reference, ap.communication, rup.name ORDER BY ''' + sql_sort)
        # params = (tuple(accounts.ids),) + tuple(where_params)
        params = (company_id[0], acc_id,) + tuple(where_params)
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
                res['cheque_no'] = line['cheque_no']
                res['description'] = line['description']
                res['create_by'] = line['create_by']
            if display_account == 'all':
                account_res.append(res)
            if display_account == 'movement' and res.get('move_lines'):
                account_res.append(res)
            if display_account == 'not_zero' and not currency.is_zero(res['balance']):
                account_res.append(res)

        return account_res

    def get_report_value(self, data=None):
        print('excel data', data)

        init_balance = data['form'].get('initial_balance', True)
        sortby = data['form'].get('sortby', 'sort_date')
        display_account = data['form']['display_account']
        coa_ids = data['form']['coa_ids']
        company_id = data['form']['company_id']
        date_from = data['form']['date_from']
        codes = []
        if data['form'].get('journal_ids', False):
            codes = [journal.code for journal in
                     self.env['account.journal'].search([('id', 'in', data['form']['journal_ids'])])]

        accounts = self.env['account.account'].search([])
        accounts_res = self.with_context(data['form'].get('used_context', {}))._get_account_move_entry(accounts,
                                                                                                       init_balance,
                                                                                                       sortby,
                                                                                                       display_account,
                                                                                                       coa_ids,
                                                                                                       company_id,
                                                                                                       date_from)
        return {

            'data': data['form'],
            'Accounts': accounts_res,
            'print_journal': codes,

        }

    def _print_report(self, data):
        data = self.pre_print_report(data)
        data['form'].update(self.read(['initial_balance', 'sortby', 'coa_ids'])[0])
        if data['form'].get('initial_balance') and not data['form'].get('date_from'):
            raise UserError(_("You must define a Start Date"))
        records = self.env[data['model']].browse(data.get('ids', []))
        return self.env.ref('gts_financial_pdf_report.action_report_general_ledger').with_context(
            landscape=True).report_action(records, data=data)

    def _print_excel_report(self, data):
        self.pre_print_report(data)
        data['form'].update(self.read(['initial_balance', 'sortby', 'coa_ids'])[0])
        dt = self.get_report_value(data)
        print(' paint data : ',dt['data'])
        report_name = self.env.user.company_id.name + " : " + 'General Ledger'
        filename = '%s : %s' % (self.env.user.company_id.name, report_name)
        print('filename', filename)
        print('reportname ', report_name)
        fp = BytesIO()

        workbook = xlsxwriter.Workbook(fp)
        wbf, workbook = utill.add_workbook_format(workbook=workbook)

        worksheet = workbook.add_worksheet(report_name)
        worksheet.merge_range('A2:I3', report_name, wbf['title_doc'])
        datas = dt['data']
        date_range = "All"
        if datas['date_from'] and datas['date_to']:
            date_range = str(datas['date_from'].strftime('%d/%m/%Y')) + " : " + str(datas['date_to'].strftime('%d/%m/%Y'))
        worksheet.merge_range('A4:I4', "Date : " + date_range,
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
            # ('JRNL', 20, 'char'),
            ('Partner', 20, 'char'),
            ('Ref', 20, 'char'),
            ('Move', 20, 'char'),
            ('Entry Label', 20, 'char'),
            ('Debit', 20, 'char'),
            ('Credit', 20, 'char'),
            ('Balance', 20, 'char'),
            ('Cheque No.', 15, 'char'),
            ('Remarks', 20, 'char'),
            ('Create By', 20, 'char'),
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
            col += 4
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
                # worksheet.write(row, col, line['lcode'])
                # col += 1
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
                worksheet.write(row, col, line['cheque_no'])
                col += 1
                worksheet.write(row, col, line['description'])
                col += 1
                worksheet.write(row, col, line['create_by'])
                col += 1
                # worksheet.write(row, col, line['amount_currency'])
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

    def add_workbook_format(self, workbook):
        colors = {
            'white_orange': '#FFFFDB',
            'orange': '#FFC300',
            'red': '#FF0000',
            'yellow': '#F6FA03',
        }

        wbf = {}
        wbf['header'] = workbook.add_format(
            {'bold': 1, 'align': 'center', 'bg_color': '#FFFFDB', 'font_color': '#000000', 'font_name': 'Arial'})
        wbf['header'].set_border()

        wbf['header_orange'] = workbook.add_format(
            {'bold': 1, 'align': 'center', 'bg_color': colors['orange'], 'font_color': '#000000',
             'font_name': 'Arial'})
        wbf['header_orange'].set_border()

        wbf['header_yellow'] = workbook.add_format(
            {'bold': 1, 'align': 'center', 'bg_color': colors['yellow'], 'font_color': '#000000',
             'font_name': 'Arial'})
        wbf['header_yellow'].set_border()

        wbf['header_no'] = workbook.add_format(
            {'bold': 1, 'align': 'center', 'bg_color': '#FFFFDB', 'font_color': '#000000', 'font_name': 'Arial'})
        wbf['header_no'].set_border()
        wbf['header_no'].set_align('vcenter')

        wbf['footer'] = workbook.add_format({'align': 'left', 'font_name': 'Arial'})

        wbf['content_datetime'] = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm:ss', 'font_name': 'Arial'})
        wbf['content_datetime'].set_left()
        wbf['content_datetime'].set_right()

        wbf['content_date'] = workbook.add_format({'num_format': 'yyyy-mm-dd', 'font_name': 'Arial'})
        wbf['content_date'].set_left()
        wbf['content_date'].set_right()

        wbf['title_doc'] = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'font_size': 20,
            'font_name': 'Arial',
        })

        wbf['company'] = workbook.add_format({'align': 'left', 'font_name': 'Arial'})
        wbf['company'].set_font_size(11)

        wbf['content'] = workbook.add_format()
        wbf['content'].set_left()
        wbf['content'].set_right()

        wbf['content_float'] = workbook.add_format({'align': 'right', 'num_format': '#,##0.00', 'font_name': 'Arial'})
        wbf['content_float'].set_right()
        wbf['content_float'].set_left()

        wbf['content_number'] = workbook.add_format({'align': 'right', 'num_format': '#,##0', 'font_name': 'Arial'})
        wbf['content_number'].set_right()
        wbf['content_number'].set_left()

        wbf['content_percent'] = workbook.add_format({'align': 'right', 'num_format': '0.00%', 'font_name': 'Arial'})
        wbf['content_percent'].set_right()
        wbf['content_percent'].set_left()

        wbf['total_float'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['white_orange'], 'align': 'right', 'num_format': '#,##0.00',
             'font_name': 'Arial'})
        wbf['total_float'].set_top()
        wbf['total_float'].set_bottom()
        wbf['total_float'].set_left()
        wbf['total_float'].set_right()

        wbf['total_number'] = workbook.add_format(
            {'align': 'right', 'bg_color': colors['white_orange'], 'bold': 1, 'num_format': '#,##0',
             'font_name': 'Arial'})
        wbf['total_number'].set_top()
        wbf['total_number'].set_bottom()
        wbf['total_number'].set_left()
        wbf['total_number'].set_right()

        wbf['total'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['white_orange'], 'align': 'center', 'font_name': 'Arial'})
        wbf['total'].set_left()
        wbf['total'].set_right()
        wbf['total'].set_top()
        wbf['total'].set_bottom()

        wbf['total_float_yellow'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['yellow'], 'align': 'right', 'num_format': '#,##0.00',
             'font_name': 'Arial'})
        wbf['total_float_yellow'].set_top()
        wbf['total_float_yellow'].set_bottom()
        wbf['total_float_yellow'].set_left()
        wbf['total_float_yellow'].set_right()

        wbf['total_number_yellow'] = workbook.add_format(
            {'align': 'right', 'bg_color': colors['yellow'], 'bold': 1, 'num_format': '#,##0', 'font_name': 'Arial'})
        wbf['total_number_yellow'].set_top()
        wbf['total_number_yellow'].set_bottom()
        wbf['total_number_yellow'].set_left()
        wbf['total_number_yellow'].set_right()

        wbf['total_yellow'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['yellow'], 'align': 'center', 'font_name': 'Arial'})
        wbf['total_yellow'].set_left()
        wbf['total_yellow'].set_right()
        wbf['total_yellow'].set_top()
        wbf['total_yellow'].set_bottom()

        wbf['total_float_orange'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['orange'], 'align': 'right', 'num_format': '#,##0.00',
             'font_name': 'Arial'})
        wbf['total_float_orange'].set_top()
        wbf['total_float_orange'].set_bottom()
        wbf['total_float_orange'].set_left()
        wbf['total_float_orange'].set_right()

        wbf['total_number_orange'] = workbook.add_format(
            {'align': 'right', 'bg_color': colors['orange'], 'bold': 1, 'num_format': '#,##0', 'font_name': 'Arial'})
        wbf['total_number_orange'].set_top()
        wbf['total_number_orange'].set_bottom()
        wbf['total_number_orange'].set_left()
        wbf['total_number_orange'].set_right()

        wbf['total_orange'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['orange'], 'align': 'center', 'font_name': 'Arial'})
        wbf['total_orange'].set_left()
        wbf['total_orange'].set_right()
        wbf['total_orange'].set_top()
        wbf['total_orange'].set_bottom()

        wbf['header_detail_space'] = workbook.add_format({'font_name': 'Arial'})
        wbf['header_detail_space'].set_left()
        wbf['header_detail_space'].set_right()
        wbf['header_detail_space'].set_top()
        wbf['header_detail_space'].set_bottom()

        wbf['header_detail'] = workbook.add_format({'bg_color': '#E0FFC2', 'font_name': 'Arial'})
        wbf['header_detail'].set_left()
        wbf['header_detail'].set_right()
        wbf['header_detail'].set_top()
        wbf['header_detail'].set_bottom()

        return wbf, workbook


class AccountCommonGeneralReport(models.TransientModel):
    _inherit = "account.report.general.ledger"

    datas = fields.Binary('File', readonly=True)
    datas_fname = fields.Char('Filename', readonly=True)
    branch_ids = fields.Many2one('res.branch', string='Branch')

    # @api.onchange('company_id')
    # def _onchange_company_id(self):
    #     if self.company_id:
    #         get_branch = self.env.user.branch_ids.filtered(lambda line: line.company_id.id == self.company_id.id)
    #         return {'domain': {'branch_ids': [('id', 'in', get_branch.ids)]}}
    #
    #     get_branch = self.env['res.branch'].search(
    #         [('id', 'in', self.env.user.branch_ids.ids), ('company_id', '=', self.env.user.company_id.id)])
    #     return {'domain': {'branch_ids': [('id', 'in', get_branch.ids)]}}
