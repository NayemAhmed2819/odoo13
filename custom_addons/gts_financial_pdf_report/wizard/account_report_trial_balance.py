# -*- coding: utf-8 -*-
import time
from odoo import api, models, _, fields
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DATE_FORMAT
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DATETIME_FORMAT, datetime, relativedelta, BytesIO, xlsxwriter, \
    base64
# from custom_addons.accounting_report.models.usl_xlxs_report_tools import UslXlxsReportUtil as utill


class AccountBalanceReport(models.TransientModel):
    _inherit = "account.common.account.report"
    _name = 'account.balance.report'
    _description = 'Trial Balance Report'

    def _get_accounts(self, accounts,init_balance, display_account, from_date, company_id, to_date,target_move):
        print(company_id, accounts, display_account, from_date)
        """ compute the balance, debit and credit for the provided accounts
            :Arguments:
                `accounts`: list of accounts record,
                `display_account`: it's used to display either all accounts or those accounts which balance is > 0
            :Returns a list of dictionary of Accounts with following key and value
                `name`: Account name,
                `code`: Account code,
                `credit`: total amount of credit,
                `debit`: total amount of debit,
                `balance`: total amount of balance,
        """

        account_result = {}
        # Prepare sql query base on selected parameters from wizard
        tables, where_clause, where_params = self.env['account.move.line']._query_get()
        tables = tables.replace('"', '')
        if not tables:
            tables = 'account_move_line'
        wheres = [""]
        if where_clause.strip():
            wheres.append(where_clause.strip())
        filters = " AND ".join(wheres)
        # compute the balance, debit and credit forgit  the provided accounts
        request = (
                "SELECT account_id AS id,0 as initial_balance, SUM(debit) AS debit, SUM(credit) AS credit, (SUM(debit) - SUM(credit)) AS balance" + \
                " FROM " + tables + " WHERE account_move_line.parent_state in ('draft', 'posted') and account_move_line.company_id= %s AND account_id IN %s " + filters + " GROUP BY account_id")
        params = (company_id[0], tuple(accounts.ids),) + tuple(where_params)
        self.env.cr.execute(request, params)
        for row in self.env.cr.dictfetchall():
            account_result[row.pop('id')] = row

        # Initial Balance Treatment start
        if from_date:
            start_date = datetime.strptime(str(from_date), DATE_FORMAT)
            account_result_ini = {}  # for initial balance
            # Initial Balance for trial Balance (add by raihan)
            # request_ini = """SELECT account_id AS id,COALESCE((SUM(debit) - SUM(credit)),0) AS initial_balance
            #                              FROM """ + tables + """ WHERE account_move_line.company_id= %s AND account_id IN %s and account_move_line.date < %s AND ("account_move_line"."move_id"="account_move_line__move_id"."id")
            #                              AND ("account_move_line__move_id"."state" in ('draft', 'posted')) """ + filters + """GROUP BY account_id"""
            #
            # params = (company_id[0], tuple(accounts.ids), start_date.strftime(DATETIME_FORMAT),) + tuple(where_params)

            where_state = ['posted']
            if target_move == 'all':
                where_state.append('draft')
            if self.initial_balance:
                request_ini = (
                        "SELECT account_id AS id,(SUM(debit) - SUM(credit)) AS initial_balance" + \
                        " FROM account_move left join account_move_line on account_move.id=account_move_line.move_id WHERE account_move_line.company_id= %s AND account_id IN %s "
                        "and account_move_line.date::DATE < %s::DATE and account_move.state in %s  GROUP BY account_id ")
                params = (company_id[0], tuple(accounts.ids), start_date.strftime(DATETIME_FORMAT), tuple(where_state))
            else:
                request_ini = (
                "SELECT account_id AS id,0 AS initial_balance" + \
                " FROM account_move left join account_move_line on account_move.id=account_move_line.move_id WHERE account_move_line.company_id= %s AND account_id IN %s "
                "and account_move_line.date::DATE < %s::DATE and account_move.state in %s  GROUP BY account_id ")
                params = (company_id[0], tuple(accounts.ids), start_date.strftime(DATETIME_FORMAT), tuple(where_state))




            self.env.cr.execute(request_ini, params)

            # self.env.cr.execute(request_ini, params)
            for init_row in self.env.cr.dictfetchall():
                account_result_ini[init_row.pop('id')] = init_row
            # request_ini = """SELECT account_id AS id,COALESCE((SUM(debit) - SUM(credit)),0) AS initial_balance
            #                      FROM {} WHERE  account_move_line.company_id= {} AND account_id IN {} and account_move_line.date< '{}' AND ("account_move_line"."move_id"="account_move_line__move_id"."id") AND ("account_move_line__move_id"."state" = 'posted') GROUP BY account_id""".format(
            #     tables, company_id[0], tuple(accounts.ids), start_date.strftime(DATETIME_FORMAT))
            #
            # self.env.cr.execute(request_ini)
            for init_row in self.env.cr.dictfetchall():
                account_result_ini[init_row.pop('id')] = init_row

            for m in account_result:
                for d in account_result_ini:
                    if m == d:
                        account_result[m]['initial_balance'] = account_result_ini[d].get('initial_balance')
                        break

            #         print(m)
            #
            # print(account_result_ini)

        account_res = []
        for account in accounts:
            res = dict((fn, 0.0) for fn in ['initial_balance', 'credit', 'debit', 'balance'])
            currency = account.currency_id and account.currency_id or account.company_id.currency_id
            res['code'] = account.code
            res['name'] = account.name

            # For Cheque In Hand and Receivable in Draft Start
            # if account.id in (576, 658):
            #     query = """select COALESCE(SUM(debit),0) - COALESCE(SUM(credit), 0) as balance, COALESCE(SUM(debit), 0) as debit, COALESCE(SUM(credit), 0) as credit from account_move_line aml
            #                 inner join account_move am on am.id = aml.move_id where account_id = {} and aml.company_id = {} and am.state in ('draft', 'posted')
            #             """.format(account.id, company_id[0])
            #     from_date_condition = "1 = 1"
            #     to_date_condition = "1 = 1"
            #     if from_date:
            #         from_date_condition = "aml.date::DATE >='" + from_date.strftime("%m-%d-%Y") + "'::DATE"
            #     if to_date:
            #         to_date_condition = "aml.date::DATE <='" + to_date.strftime("%m-%d-%Y") + "'::DATE"
            #     # if from_date and to_date:
            #     query = """select COALESCE(SUM(debit),0) - COALESCE(SUM(credit), 0) as balance, COALESCE(SUM(debit), 0) as debit, COALESCE(SUM(credit), 0) as credit from account_move_line aml
            #                 inner join account_move am on am.id = aml.move_id where account_id = {} and aml.company_id = {} and am.state in ('draft', 'posted') and {} and {}
            #             """.format(account.id, company_id[0], from_date_condition, to_date_condition)
            #
            #     query_ini = """select COALESCE((SUM(debit) - SUM(credit)),0) AS initial_balance from account_move_line aml inner join account_move as am on am.id = aml.move_id where aml.account_id = {}
            #             and aml.company_id = {} and am.state in ('draft', 'posted') and aml.date::DATE < '{}'::DATE """.format(account.id, company_id[0], from_date)
            #
            #     self._cr.execute(query_ini)
            #     init_value = self.env.cr.dictfetchall()
            #     if init_value:
            #         account_result[account.id]['initial_balance'] = init_value[0]['initial_balance']
            #
            #     self._cr.execute(query)
            #     list_value = self._cr.dictfetchall()
            #
            #     if list_value:
            #         account_result[account.id]['debit'] = list_value[0]['debit']
            #         account_result[account.id]['credit'] = list_value[0]['credit']
            #         account_result[account.id]['balance'] = list_value[0]['balance']
            # For Cheque In Hand and Receivable in Draft End

            if account.id in account_result:
                res['initial_balance'] = account_result[account.id].get('initial_balance')
                res['debit'] = account_result[account.id].get('debit')
                res['credit'] = account_result[account.id].get('credit')
                res['balance'] = account_result[account.id].get('balance')
            if display_account == 'all':
                account_res.append(res)
            if display_account == 'not_zero' and not currency.is_zero(res['balance']):
                account_res.append(res)
            if display_account == 'movement' and (
                    not currency.is_zero(res['debit']) or not currency.is_zero(res['credit'])):
                account_res.append(res)
        print('account res : ', account_res)
        return account_res

    def get_report_value(self, data=None):

        self.model = self.env.context.get('active_model')

        display_account = data['form'].get('display_account')
        accounts = self.env['account.account'].search([])
        company_id = data['form']['company_id']
        from_date = data['form']['date_from']
        to_date = data['form']['date_to']
        target_move=data['form']['target_move']
        init_balance = data['form'].get('initial_balance', True)
        account_res = self.with_context(data['form'].get('used_context'))._get_accounts(accounts,init_balance, display_account,
                                                                                        from_date, company_id, to_date,target_move)


        return {

            'data': data['form'],

            'Accounts': account_res,
        }

    journal_ids = fields.Many2many('account.journal', 'account_balance_report_journal_rel', 'account_id', 'journal_id',
                                   string='Journals', required=True, default=[])

    def _print_report(self, data):
        data = self.pre_print_report(data)
        data['form'].update(self.read(['initial_balance'])[0])
        if data['form'].get('initial_balance') and not data['form'].get('date_from'):
            raise UserError(_("You must define a Start Date"))
        records = self.env[data['model']].browse(data.get('ids', []))
        return self.env.ref('gts_financial_pdf_report.action_report_trial_balance').report_action(records, data=data)

    def _print_excel_report(self, data):

        self.pre_print_report(data)
        data = self.get_report_value(data)
        report_name = self.env.user.company_id.name + " : " + 'Trail Balance Report'
        print(report_name)
        filename = '%s : %s' % (self.env.user.company_id.name, report_name)
        fp = BytesIO()
        workbook = xlsxwriter.Workbook(fp)
        wbf, workbook = utill.add_workbook_format(workbook)

        worksheet = workbook.add_worksheet(report_name)
        worksheet.merge_range('A2:I3', report_name, wbf['title_doc'])
        wbf_value =wbf['header_detail']
        worksheet.merge_range('A6:B6', 'Display Account', wbf_value)
        datas = data['data']
        display_account = None
        if datas['display_account'] == 'all':
            display_account = 'All accounts'
        elif datas['display_account'] == 'movement':
            display_account = 'With movements'
        elif datas['display_account'] == 'not_zero':
            display_account = 'With balance not equal to zero'

        worksheet.merge_range('A7:B7', display_account,
                              wbf['header_detail'])
        worksheet.write(5, 3, 'Date Form : ', wbf['header_detail'])
        worksheet.write(5, 4, str(datas['date_from']), wbf['header_detail'])
        worksheet.write(6, 3, 'Date Form : ', wbf['header_detail'])
        worksheet.write(6, 4, str(datas['date_from']), wbf['header_detail'])
        worksheet.merge_range('G6:H6', "Target Moves",
                              wbf['header_detail'])
        target_move = None
        if datas['target_move'] == 'all':
            target_move = 'All Entries'
        elif datas['target_move'] == 'posted':
            target_move = 'All Posted Entries'

        worksheet.merge_range('G7:H7', target_move,
                              wbf['header_detail'])
        worksheet.merge_range('J6:K6', "Branch",
                              wbf['header_detail'])
        if self.branch_ids:
            worksheet.merge_range('J7:K7', self.branch_ids.name,
                                  wbf['header_detail'])

        row = 10
        column_name = [
            ('Code', 15, 'char'),
            ('Account', 20, 'char'),
            ('Initial Balance', 20, 'char'),
            ('Debit', 20, 'char'),
            ('Credit', 20, 'char'),
            ('Balance', 20, 'char'),

        ]
        col = 0
        for column in column_name:
            column_name = column[0]
            column_width = column[1]
            worksheet.set_column(col, col, column_width)
            worksheet.write(row, col, column_name, wbf['header_orange'])
            col += 1
        row += 1
        accounts = data['Accounts']
        debit_total = 0
        credit_total = 0
        balance_total = 0
        for account in accounts:
            col = 0
            wbf_value = wbf['content']
            worksheet.write(row, col, account['code'] )
            col += 1
            worksheet.write(row, col, account['name'])
            col += 1
            worksheet.write(row, col, account['initial_balance'],wbf_value)
            col += 1
            worksheet.write(row, col, account['debit'],wbf_value)
            col += 1
            worksheet.write(row, col, account['credit'],wbf_value)
            col += 1
            worksheet.write(row, col, (account['initial_balance'] + account['balance']),wbf_value)
            debit_total += account['debit']
            credit_total += account['credit']
            balance_total += (account['initial_balance'] + account['balance'])
            col += 1
            row += 1
            worksheet.write(row, 0, 'Total', wbf['header_orange'])
            worksheet.write(row, 1, '', wbf['header_orange'])
            worksheet.write(row, 2, '', wbf['header_orange'])
            worksheet.write(row, 3, debit_total, wbf['header_orange'])
            worksheet.write(row, 4, credit_total, wbf['header_orange'])
            worksheet.write(row, 5, balance_total, wbf['header_orange'])

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
            {'bold': 1, 'align': 'center', 'bg_color': '#FFFFDB', 'font_color': '#000000', 'font_name': 'Calibri'})
        wbf['header'].set_border()

        wbf['header_orange'] = workbook.add_format(
            {'bold': 1, 'align': 'center', 'bg_color': colors['orange'], 'font_color': '#000000',
             'font_name': 'Calibri'})
        wbf['header_orange'].set_border()

        wbf['header_yellow'] = workbook.add_format(
            {'bold': 1, 'align': 'center', 'bg_color': colors['yellow'], 'font_color': '#000000',
             'font_name': 'Calibri'})
        wbf['header_yellow'].set_border()

        wbf['header_no'] = workbook.add_format(
            {'bold': 1, 'align': 'center', 'bg_color': '#FFFFDB', 'font_color': '#000000', 'font_name': 'Calibri'})
        wbf['header_no'].set_border()
        wbf['header_no'].set_align('vcenter')

        wbf['footer'] = workbook.add_format({'align': 'left', 'font_name': 'Calibri'})

        wbf['content_datetime'] = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm:ss', 'font_name': 'Calibri'})
        wbf['content_datetime'].set_left()
        wbf['content_datetime'].set_right()

        wbf['content_date'] = workbook.add_format({'num_format': 'yyyy-mm-dd', 'font_name': 'Calibri'})
        wbf['content_date'].set_left()
        wbf['content_date'].set_right()

        wbf['title_doc'] = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'font_size': 20,
            'font_name': 'Calibri',
        })

        wbf['company'] = workbook.add_format({'align': 'left', 'font_name': 'Calibri'})
        wbf['company'].set_font_size(11)

        wbf['content'] = workbook.add_format()
        wbf['content'].set_left()
        wbf['content'].set_right()

        wbf['content_float'] = workbook.add_format({'align': 'right', 'num_format': '#,##0.00', 'font_name': 'Calibri'})
        wbf['content_float'].set_right()
        wbf['content_float'].set_left()

        wbf['content_number'] = workbook.add_format({'align': 'right', 'num_format': '#,##0', 'font_name': 'Calibri'})
        wbf['content_number'].set_right()
        wbf['content_number'].set_left()

        wbf['content_percent'] = workbook.add_format({'align': 'right', 'num_format': '0.00%', 'font_name': 'Calibri'})
        wbf['content_percent'].set_right()
        wbf['content_percent'].set_left()

        wbf['total_float'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['white_orange'], 'align': 'right', 'num_format': '#,##0.00',
             'font_name': 'Calibri'})
        wbf['total_float'].set_top()
        wbf['total_float'].set_bottom()
        wbf['total_float'].set_left()
        wbf['total_float'].set_right()

        wbf['total_number'] = workbook.add_format(
            {'align': 'right', 'bg_color': colors['white_orange'], 'bold': 1, 'num_format': '#,##0',
             'font_name': 'Calibri'})
        wbf['total_number'].set_top()
        wbf['total_number'].set_bottom()
        wbf['total_number'].set_left()
        wbf['total_number'].set_right()

        wbf['total'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['white_orange'], 'align': 'center', 'font_name': 'Calibri'})
        wbf['total'].set_left()
        wbf['total'].set_right()
        wbf['total'].set_top()
        wbf['total'].set_bottom()

        wbf['total_float_yellow'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['yellow'], 'align': 'right', 'num_format': '#,##0.00',
             'font_name': 'Calibri'})
        wbf['total_float_yellow'].set_top()
        wbf['total_float_yellow'].set_bottom()
        wbf['total_float_yellow'].set_left()
        wbf['total_float_yellow'].set_right()

        wbf['total_number_yellow'] = workbook.add_format(
            {'align': 'right', 'bg_color': colors['yellow'], 'bold': 1, 'num_format': '#,##0', 'font_name': 'Calibri'})
        wbf['total_number_yellow'].set_top()
        wbf['total_number_yellow'].set_bottom()
        wbf['total_number_yellow'].set_left()
        wbf['total_number_yellow'].set_right()

        wbf['total_yellow'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['yellow'], 'align': 'center', 'font_name': 'Calibri'})
        wbf['total_yellow'].set_left()
        wbf['total_yellow'].set_right()
        wbf['total_yellow'].set_top()
        wbf['total_yellow'].set_bottom()

        wbf['total_float_orange'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['orange'], 'align': 'right', 'num_format': '#,##0.00',
             'font_name': 'Calibri'})
        wbf['total_float_orange'].set_top()
        wbf['total_float_orange'].set_bottom()
        wbf['total_float_orange'].set_left()
        wbf['total_float_orange'].set_right()

        wbf['total_number_orange'] = workbook.add_format(
            {'align': 'right', 'bg_color': colors['orange'], 'bold': 1, 'num_format': '#,##0', 'font_name': 'Calibri'})
        wbf['total_number_orange'].set_top()
        wbf['total_number_orange'].set_bottom()
        wbf['total_number_orange'].set_left()
        wbf['total_number_orange'].set_right()

        wbf['total_orange'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['orange'], 'align': 'center', 'font_name': 'Calibri'})
        wbf['total_orange'].set_left()
        wbf['total_orange'].set_right()
        wbf['total_orange'].set_top()
        wbf['total_orange'].set_bottom()

        wbf['header_detail_space'] = workbook.add_format({'font_name': 'Calibri'})
        wbf['header_detail_space'].set_left()
        wbf['header_detail_space'].set_right()
        wbf['header_detail_space'].set_top()
        wbf['header_detail_space'].set_bottom()

        wbf['header_detail'] = workbook.add_format({'bg_color': '#E0FFC2', 'font_name': 'Calibri'})
        wbf['header_detail'].set_left()
        wbf['header_detail'].set_right()
        wbf['header_detail'].set_top()
        wbf['header_detail'].set_bottom()

        return wbf, workbook


class AccountBalanceReport(models.TransientModel):
    _inherit = "account.balance.report"

    branch_ids = fields.Many2one('res.branch', string='Branch')
    datas = fields.Binary('File', readonly=True)
    datas_fname = fields.Char('Filename', readonly=True)

    # @api.onchange('company_id')
    # def _onchange_company_id(self):
    #     if self.company_id:
    #         get_branch = self.env.user.branch_ids.filtered(lambda line: line.company_id.id == self.company_id.id)
    #         return {'domain': {'branch_ids': [('id', 'in', get_branch.ids)]}}
    #
    #     get_branch = self.env['res.branch'].search(
    #         [('id', 'in', self.env.user.branch_ids.ids), ('company_id', '=', self.env.user.company_id.id)])
    #     return {'domain': {'branch_ids': [('id', 'in', get_branch.ids)]}}
