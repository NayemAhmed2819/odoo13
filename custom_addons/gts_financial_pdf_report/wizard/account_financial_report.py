from odoo import api, fields, models
from odoo.tools import get_lang
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import get_lang
import base64
from odoo import fields, models, api
from io import BytesIO
from odoo.tools import xlsxwriter
from datetime import datetime
from pytz import timezone
import pytz


class AccountingReport(models.TransientModel):
    _name = "accounting.report"
    _inherit = "account.common.report"
    _description = "Accounting Report"

    with_buffer_stock = fields.Boolean("With Buffer Stock", default=False)

    @api.model
    def _get_account_report(self):
        reports = []
        if self._context.get('active_id'):
            menu = self.env['ir.ui.menu'].browse(self._context.get('active_id')).name
            reports = self.env['account.financial.report'].search([('name', 'ilike', menu), ('company_id', '=', self.company_id.id)])
        return reports and reports[0] or False

    enable_filter = fields.Boolean(string='Enable Comparison')
    # account_report_id = fields.Many2one('account.financial.report', string='Account Reports', required=True, default=_get_account_report)
    account_report_id = fields.Many2one('account.financial.report', string='Account Reports', required=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    label_filter = fields.Char(string='Column Label', help="This label will be displayed on report to show the balance computed for the given comparison filter.")
    filter_cmp = fields.Selection([('filter_no', 'No Filters'), ('filter_date', 'Date')], string='Filter by', required=True, default='filter_no')
    date_from_cmp = fields.Date(string='Start Date')
    date_to_cmp = fields.Date(string='End Date')
    debit_credit = fields.Boolean(string='Display Debit/Credit Columns', help="This option allows you to get more details about the way your balances are computed. Because it is space consuming, we do not allow to use it while doing a comparison.")
    datas = fields.Binary('File', readonly=True)
    datas_fname = fields.Char('Filename', readonly=True)

    @api.onchange("company_id")
    def _onchange_company_id(self):
        domain = {'domain': {'account_report_id': [('parent_id', '=', False), ('company_id', '=', self.company_id.id)]}}
        return domain

    def _build_comparison_context(self, data):
        result = {}
        result['journal_ids'] = 'journal_ids' in data['form'] and data['form']['journal_ids'] or False
        result['state'] = 'target_move' in data['form'] and data['form']['target_move'] or ''
        if data['form']['filter_cmp'] == 'filter_date':
            result['date_from'] = data['form']['date_from_cmp']
            result['date_to'] = data['form']['date_to_cmp']
            result['strict_range'] = True
        return result

    def _compute_account_balance(self, accounts,company_id):
        # print('yes here checked 2')

        """ compute the balance, debit and credit for the provided accounts
        """
        # print(self)
        # print(accounts)
        mapping = {
            'balance': "COALESCE(SUM(debit),0) - COALESCE(SUM(credit), 0) as balance",
            'debit': "COALESCE(SUM(debit), 0) as debit",
            'credit': "COALESCE(SUM(credit), 0) as credit",
        }

        res = {}
        for account in accounts:
            res[account.id] = dict.fromkeys(mapping, 0.0)
        if accounts:
            tables, where_clause, where_params = self.env['account.move.line']._query_get()
            tables = tables.replace('"', '') if tables else "account_move_line"
            wheres = [""]
            if where_clause.strip():
                wheres.append(where_clause.strip())
            filters = " AND ".join(wheres)
            request = "SELECT account_id as id, " + ', '.join(mapping.values()) + \
                       " FROM " + tables + \
                       " WHERE account_move_line.parent_state in ('draft', 'posted') and account_move_line.company_id="\
                            + str(company_id) +\
                          " AND account_id IN %s " \
                            + filters + \
                       " GROUP BY account_id"
            params = (tuple(accounts._ids),) + tuple(where_params)
            self.env.cr.execute(request, params)
            for row in self.env.cr.dictfetchall():
                res[row['id']] = row
        return res

    def _compute_report_balance(self, reports,company_id, data):
        # print('yes here checked 3')

        '''returns a dictionary with key=the ID of a record and value=the credit, debit and balance amount
           computed for this record. If the record is of type :
               'accounts' : it's the sum of the linked accounts
               'account_type' : it's the sum of leaf accoutns with such an account_type
               'account_report' : it's the amount of the related report
               'sum' : it's the sum of the children of this record (aka a 'view' record)'''
        res = {}
        fields = ['credit', 'debit', 'balance']
        for report in reports:
            if report.id in res:
                continue
            res[report.id] = dict((fn, 0.0) for fn in fields)
            if report.type == 'accounts':
                # it's the sum of the linked accounts
                res[report.id]['account'] = self._compute_account_balance(report.account_ids,company_id)
                for value in res[report.id]['account'].values():

                    # For Cheque In Hand and Receivable in Draft Start
                    # if 'id' in value.keys():
                    #     val_id = value.get('id')
                    #     if val_id in (576, 658):
                    #         from_date_condition = "1=1"
                    #         to_date_condition = "1=1"
                    #         if data.get('date_from'):
                    #             from_date_condition = "aml.date::DATE >='" + data.get('date_from').strftime("%d-%m-%Y") + "'::DATE"
                    #         if data.get('date_to'):
                    #             to_date_condition = "aml.date::DATE <='" + data.get('date_to').strftime("%d-%m-%Y") + "'::DATE"
                    #
                    #         query = """select COALESCE(SUM(debit),0) - COALESCE(SUM(credit), 0) as balance, COALESCE(SUM(debit), 0) as debit, COALESCE(SUM(credit), 0) as credit from account_move_line aml
                    #                     inner join account_move am on am.id = aml.move_id where account_id = {} and aml.company_id = {} and am.state in ('draft', 'posted') and {} and {}
                    #                 """.format(val_id, company_id, from_date_condition, to_date_condition)
                    #         self._cr.execute(query)
                    #         list_value = self._cr.dictfetchall()
                    #         value = list_value[0]
                    # For Cheque In Hand and Receivable in Draft End

                    for field in fields:
                        res[report.id][field] += value.get(field)
            elif report.type == 'account_type':
                # it's the sum the leaf accounts with such an account type
                accounts = self.env['account.account'].search([('user_type_id', 'in', report.account_type_ids.ids)])
                res[report.id]['account'] = self._compute_account_balance(accounts,company_id)
                for value in res[report.id]['account'].values():
                    for field in fields:
                        res[report.id][field] += value.get(field)
            elif report.type == 'account_report' and report.account_report_id:
                # it's the amount of the linked report
                res2 = self._compute_report_balance(report.account_report_id,company_id, data)
                for key, value in res2.items():
                    for field in fields:
                        res[report.id][field] += value[field]
            elif report.type == 'sum':
                # it's the sum of the children of this account.report
                res2 = self._compute_report_balance(report.children_ids,company_id, data)
                for key, value in res2.items():
                    for field in fields:
                        res[report.id][field] += value[field]
        return res

    def get_account_lines(self, data):
        # print('yes here checked 2')
        company_id =data["company_id"][0]
        lines = []
        account_report = self.env['account.financial.report'].search([('id', '=', data['account_report_id'][0])])
        # print('account_report is',account_report)
        child_reports = account_report._get_children_by_order()
        res = self.with_context(data.get('used_context'))._compute_report_balance(child_reports,company_id, data)
        if data['enable_filter']:
            comparison_res = self.with_context(data.get('comparison_context'))._compute_report_balance(child_reports,company_id, data)
            for report_id, value in comparison_res.items():
                res[report_id]['comp_bal'] = value['balance']
                report_acc = res[report_id].get('account')
                if report_acc:
                    for account_id, val in comparison_res[report_id].get('account').items():
                        report_acc[account_id]['comp_bal'] = val['balance']

        for report in child_reports:
            vals = {
                'name': report.name,
                'balance': res[report.id]['balance'] * float(report.sign) or 0.0,
                'type': 'report',
                'level': bool(report.style_overwrite) and report.style_overwrite or report.level,
                'account_type': report.type or False, #used to underline the financial report balances
            }
            if data['debit_credit']:
                vals['debit'] = res[report.id]['debit']
                vals['credit'] = res[report.id]['credit']

            if data['enable_filter']:
                vals['balance_cmp'] = res[report.id]['comp_bal'] * float(report.sign)

            lines.append(vals)
            if report.display_detail == 'no_detail':
                #the rest of the loop is used to display the details of the financial report, so it's not needed here.
                continue

            if res[report.id].get('account'):
                sub_lines = []
                for account_id, value in res[report.id]['account'].items():
                    #if there are accounts to display, we add them to the lines with a level equals to their level in
                    #the COA + 1 (to avoid having them with a too low level that would conflicts with the level of data
                    #financial reports for Assets, liabilities...)
                    flag = False
                    account = self.env['account.account'].browse(account_id)

                    # For Cheque In Hand and Receivable in Draft Start
                    # if account_id in (576, 658):
                    #     from_date_condition = "1=1"
                    #     to_date_condition = "1=1"
                    #     if data.get('date_from'):
                    #         from_date_condition = "aml.date::DATE >='" + data.get('date_from').strftime("%d-%m-%Y") + "'::DATE"
                    #     if data.get('date_to'):
                    #         to_date_condition = "aml.date::DATE <='" + data.get('date_to').strftime("%d-%m-%Y") + "'::DATE"
                    #
                    #     query = """select COALESCE(SUM(debit),0) - COALESCE(SUM(credit), 0) as balance, COALESCE(SUM(debit), 0) as debit, COALESCE(SUM(credit), 0) as credit from account_move_line aml
                    #                 inner join account_move am on am.id = aml.move_id where account_id = {} and aml.company_id = {} and am.state in ('draft', 'posted') and {} and {}
                    #             """.format(account_id, company_id, from_date_condition, to_date_condition)
                    #     self._cr.execute(query)
                    #     list_value = self._cr.dictfetchall()
                    #     value = list_value[0]
                    #     value['comp_bal'] = value['balance']
                    # For Cheque In Hand and Receivable in Draft End

                    vals = {
                        'name': account.code + ' ' + account.name,
                        'balance': value['balance'] * float(report.sign) or 0,
                        'type': 'account',
                        'level': report.display_detail == 'detail_with_hierarchy' and 4,
                        'account_type': account.internal_type,
                    }
                    if data['debit_credit']:
                        vals['debit'] = value['debit']
                        vals['credit'] = value['credit']
                        if not account.company_id.currency_id.is_zero(vals['debit']) or not account.company_id.currency_id.is_zero(vals['credit']):
                            flag = True
                    if not account.company_id.currency_id.is_zero(vals['balance']):
                        flag = True
                    if data['enable_filter']:
                        vals['balance_cmp'] = value['comp_bal'] * float(report.sign)
                        if not account.company_id.currency_id.is_zero(vals['balance_cmp']):
                            flag = True
                    if flag:
                        sub_lines.append(vals)
                lines += sorted(sub_lines, key=lambda sub_line: sub_line['name'])
        return lines

    # def check_report(self):
    #     print("Hello Me")
    #     return super(AccountingReport, self).check_report()
    #     data = {}
    #     data['form'] = self.read(['account_report_id', 'date_from_cmp', 'date_to_cmp', 'journal_ids', 'filter_cmp', 'target_move'])[0]
    #     for field in ['account_report_id']:
    #         if isinstance(data['form'][field], tuple):
    #             data['form'][field] = data['form'][field][0]
    #     comparison_context = self._build_comparison_context(data)
    #     res['data']['form']['comparison_context'] = comparison_context
    #     return res

    def _print_report(self, data):
        account_report = self.env['account.financial.report'].search([('id', '=', self.account_report_id.id), ('company_id', '=', self.company_id.id)])
        if not account_report:
            account_report_by_name = self.env['account.financial.report'].search([('name', '=', self.account_report_id.name), ('company_id', '=', self.company_id.id)])
            if not account_report_by_name:
                raise UserError(_("Selected Account Reports is not valid. \nPlease recheck Account Reports"))
            else:
                self.account_report_id = account_report_by_name

        data['form'].update(self.read(['date_from_cmp', 'debit_credit', 'date_to_cmp', 'filter_cmp', 'account_report_id', 'enable_filter', 'label_filter', 'target_move', 'with_buffer_stock'])[0])
        return self.env.ref('gts_financial_pdf_report.action_report_financial').report_action(self, data=data, config=False)

    def print_excel_report(self):

        account_report = self.env['account.financial.report'].search([('id', '=', self.account_report_id.id), ('company_id', '=', self.company_id.id)])
        if not account_report:
            account_report_by_name = self.env['account.financial.report'].search([('name', '=', self.account_report_id.name), ('company_id', '=', self.company_id.id)])
            if not account_report_by_name:
                raise UserError(_("Selected Account Reports is not valid. \nPlease recheck Account Reports"))
            else:
                self.account_report_id = account_report_by_name

        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(['date_from', 'date_to', 'journal_ids', 'target_move', 'company_id'])[0]
        used_context = self._build_contexts(data) # build_context is a function of parent class,so you can browse this
        data['form']['used_context'] = dict(used_context, lang=get_lang(self.env).code)
        # return self.with_context(discard_logo_check=True)._print_report(data)
        # print('The ultimate data is', data)
        # print('Yes here checked')
        # print('checked checked')

        data['form'].update(self.read(['date_from_cmp', 'debit_credit', 'date_to_cmp', 'filter_cmp', 'account_report_id', 'enable_filter', 'label_filter', 'target_move'])[0])
        # print('the last data is',data)
        # print('excel report')
        # self.model = self.env.context.get('active_model')
        # docs = self.env[self.model].browse(self.env.context.get('active_id'))
        # print('docs is',docs)
        report_lines = self.get_account_lines(data.get('form')) # 'get_account_lines' is a function of abstract model, in PDF it call into abstract model but in excel report it can't, for that reason we have to write all function of abstract model inside the transient model class
        # print('report lines is', report_lines)
        # return {
        #     'doc_ids': self.ids,
        #     'doc_model': self.model,
        #     'data': data['form'],
        #     'docs': docs,
        #     'time': time,
        #     'get_account_lines': report_lines,
        # }


        report_name = data['form']['account_report_id'][1]
        filename = '%s' % (report_name)

        fp = BytesIO()
        workbook = xlsxwriter.Workbook(fp)
        wbf, workbook = self.add_workbook_format(workbook)
        worksheet = workbook.add_worksheet(report_name)
        worksheet.merge_range('A2:I3', report_name, wbf['title_doc'])

        # column_product = [
        #     ('Partners',24,'char','char'),
        #     ('Not due',12,'float','float'),
        #     ('0-30',13,'float','float'),
        #     ('30-60',13,'float','float'),
        #     ('60-90',14,'float','float'),
        #     ('90-120',14,'float','float'),
        #     ('+120',10,'float','float'),
        #     ('Total',17,'float','float')
        # ]
        row = 5
        worksheet.merge_range('A%s:B%s' % (row - 1, row - 1), 'Target Moves', wbf['header_orange'])
        # worksheet.merge_range('D%s:E%s' % (row - 1, row - 1), 'Period Length(days)', wbf['header_orange'])
        row += 1
        if data['form']['target_move'] == 'all':
            worksheet.merge_range('A%s:B%s' % (row - 1, row - 1), 'All Entries',wbf['header_detail'])
        if data['form']['target_move'] == 'posted':
            worksheet.merge_range('A%s:B%s' % (row - 1, row - 1), 'All Posted Entries',wbf['header_detail'])
        row += 1

        worksheet.merge_range('A%s:B%s' % (row-1,row-1), 'Date from : ' + str(data['form']['date_from']),wbf['header_orange'])
        row += 1
        worksheet.merge_range('A%s:B%s' % (row-1,row-1), 'Date to : ' + str(data['form']['date_to']), wbf['header_orange'])
        # worksheet.merge_range('C%s:D%s' % (row-1,row-1), str(data['form']['date_to']))
        row += 1
        worksheet.merge_range('A%s:B%s' % (row-1,row-1), 'Branch: ' + data['form']['used_context']['branch_ids'],wbf['header_orange'])
        # worksheet.merge_range('C%s:D%s' % (row-1,row-1), data['form']['used_context']['branch_ids'])
        row += 1

        Debit_credit_column = [
            ('Name',29,'char','char'),
            ('Debit',17,'float','float'),
            ('Credit',17,'float','float'),
            ('Balance',18,'float','float')
        ]

        Column = [
            ('Name',40,'char','char'),
            ('Balance',47,'float','float')
        ]
        query_buffer_stock = """
            select COALESCE(sum(COALESCE(sq.quantity, 0)*COALESCE(ip.value_float, 0)), 0) as total_buffer_stock_value from stock_quant as sq
                left join product_product as pp on pp.id = sq.product_id
                left join ir_property as ip on ip.res_id = 'product.template'||pp.product_tmpl_id
                where sq.location_id = 449"""
        self._cr.execute(query=query_buffer_stock)
        value = self._cr.fetchall()

        if data['form']['debit_credit']:
            col2 = 0
            for header in Debit_credit_column:
                header_name = header[0]
                header_width = header[1]
                worksheet.set_column(col2,col2,header_width)
                worksheet.write(row-1,col2,header_name,wbf['header_detail'])
                col2 += 1
            row += 1

            if self.with_buffer_stock:
                for line in report_lines:
                    col3 = 0
                    if line['level']:
                        worksheet.write(row-1,col3,line['name'])
                        col3 += 1
                        worksheet.write(row-1,col3,line['debit'])
                        col3 += 1
                        worksheet.write(row-1,col3,line['credit'])
                        col3 += 1
                        worksheet.write(row-1,col3,line['balance'])
                        row += 1
                        if line['name'] == '110100 Stock Valuation':
                            col3 = 0
                            worksheet.write(row-1, col3, "Buffer Stock", wbf['buffer_stock'])
                            col3 += 1
                            worksheet.write(row-1, col3, 0, wbf['buffer_stock_amt'])
                            col3 += 1
                            worksheet.write(row-1, col3, 0, wbf['buffer_stock_amt'])
                            col3 += 1
                            worksheet.write(row-1, col3, value[0][0], wbf['buffer_stock_amt'])
                            row += 1
            else:
                for line in report_lines:
                    col3 = 0
                    if line['level']:
                        worksheet.write(row-1,col3,line['name'])
                        col3 += 1
                        worksheet.write(row-1,col3,line['debit'])
                        col3 += 1
                        worksheet.write(row-1,col3,line['credit'])
                        col3 += 1
                        worksheet.write(row-1,col3,line['balance'])
                        row += 1

        if not data['form']['enable_filter'] and not data['form']['debit_credit']:
            col4 = 0
            for head in Column:
                head_name = head[0]
                head_width = head[1]
                worksheet.set_column(col4,col4,head_width)
                worksheet.write(row-1,col4,head_name,wbf['header_detail'])
                col4 += 1
            row += 1

            for line2 in report_lines:
                col5 = 0
                if self.with_buffer_stock:
                    if line2['level']:
                        worksheet.write(row-1,col5,line2['name'])
                        col5 += 1
                        worksheet.write(row-1,col5,line2['balance'])
                        row += 1
                        if line2['name'] == '110100 Stock Valuation':
                            col5 = 0
                            worksheet.write(row-1, col5, "Buffer Stock", wbf['buffer_stock'])
                            col5 += 1
                            worksheet.write(row-1, col5, value[0][0], wbf['buffer_stock_amt'])
                            row += 1
                else:
                    if line2['level']:
                        worksheet.write(row-1,col5,line2['name'])
                        col5 += 1
                        worksheet.write(row-1,col5,line2['balance'])
                        row += 1

        if data['form']['enable_filter'] and not data['form']['debit_credit']:
            col6 = 0
            for head2 in Column:
                head2_name = head2[0]
                head2_width = head2[1]
                worksheet.set_column(col6,col6,head2_width)
                worksheet.write(row-1,col6,head2_name,wbf['header_detail'])
                col6 += 1
            row += 1

            for line3 in report_lines:
                col7 = 0
                if self.with_buffer_stock:
                    if line3['level']:
                        worksheet.write(row-1,col7,line3['name'])
                        col7 += 1
                        worksheet.write(row-1,col7,line3['balance'])
                        col7 += 1
                        worksheet.write(row-1,col7,line3['balance_emp'])
                        row += 1
                        if line3['name'] == '110100 Stock Valuation':
                            col7 = 0
                            worksheet.write(row-1, col7, "Buffer Stock", wbf['buffer_stock'])
                            col7 += 1
                            worksheet.write(row-1, col7, value[0][0], wbf['buffer_stock_amt'])
                            row += 1
                else:
                    if line3['level']:
                        worksheet.write(row-1,col7,line3['name'])
                        col7 += 1
                        worksheet.write(row-1,col7,line3['balance'])
                        col7 += 1
                        worksheet.write(row-1,col7,line3['balance_emp'])
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
            {'bold': 1, 'align': 'center', 'bg_color': '#FFFFDB', 'font_color': '#000000', 'font_name': 'Georgia'})
        wbf['header'].set_border()

        wbf['header_orange'] = workbook.add_format(
            {'bold': 1, 'align': 'center', 'bg_color': colors['orange'], 'font_color': '#000000',
             'font_name': 'Georgia'})
        wbf['header_orange'].set_border()

        wbf['header_yellow'] = workbook.add_format(
            {'bold': 1, 'align': 'center', 'bg_color': colors['yellow'], 'font_color': '#000000',
             'font_name': 'Georgia'})
        wbf['header_yellow'].set_border()

        wbf['header_no'] = workbook.add_format(
            {'bold': 1, 'align': 'center', 'bg_color': '#FFFFDB', 'font_color': '#000000', 'font_name': 'Georgia'})
        wbf['header_no'].set_border()
        wbf['header_no'].set_align('vcenter')

        wbf['footer'] = workbook.add_format({'align': 'left', 'font_name': 'Georgia'})

        wbf['content_datetime'] = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm:ss', 'font_name': 'Georgia'})
        wbf['content_datetime'].set_left()
        wbf['content_datetime'].set_right()

        wbf['content_date'] = workbook.add_format({'num_format': 'yyyy-mm-dd', 'font_name': 'Georgia'})
        wbf['content_date'].set_left()
        wbf['content_date'].set_right()

        wbf['title_doc'] = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'font_size': 20,
            'font_name': 'Georgia',
        })
        wbf['buffer_stock'] = workbook.add_format({'align': 'left'})
        wbf['buffer_stock'].set_font_color('#00FFFF')
        wbf['buffer_stock_amt'] = workbook.add_format({'align': 'right', 'num_format': '#,##0.00'})
        wbf['buffer_stock_amt'].set_font_color('#00FFFF')

        wbf['company'] = workbook.add_format({'align': 'left', 'font_name': 'Georgia'})
        wbf['company'].set_font_size(11)

        wbf['content'] = workbook.add_format()
        wbf['content'].set_left()
        wbf['content'].set_right()

        wbf['content_float'] = workbook.add_format({'align': 'right', 'num_format': '#,##0.00', 'font_name': 'Georgia'})
        wbf['content_float'].set_right()
        wbf['content_float'].set_left()

        wbf['content_number'] = workbook.add_format({'align': 'right', 'num_format': '#,##0', 'font_name': 'Georgia'})
        wbf['content_number'].set_right()
        wbf['content_number'].set_left()

        wbf['content_percent'] = workbook.add_format({'align': 'right', 'num_format': '0.00%', 'font_name': 'Georgia'})
        wbf['content_percent'].set_right()
        wbf['content_percent'].set_left()

        wbf['total_float'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['white_orange'], 'align': 'right', 'num_format': '#,##0.00',
             'font_name': 'Georgia'})
        wbf['total_float'].set_top()
        wbf['total_float'].set_bottom()
        wbf['total_float'].set_left()
        wbf['total_float'].set_right()

        wbf['total_number'] = workbook.add_format(
            {'align': 'right', 'bg_color': colors['white_orange'], 'bold': 1, 'num_format': '#,##0',
             'font_name': 'Georgia'})
        wbf['total_number'].set_top()
        wbf['total_number'].set_bottom()
        wbf['total_number'].set_left()
        wbf['total_number'].set_right()

        wbf['total'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['white_orange'], 'align': 'center', 'font_name': 'Georgia'})
        wbf['total'].set_left()
        wbf['total'].set_right()
        wbf['total'].set_top()
        wbf['total'].set_bottom()

        wbf['total_float_yellow'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['yellow'], 'align': 'right', 'num_format': '#,##0.00',
             'font_name': 'Georgia'})
        wbf['total_float_yellow'].set_top()
        wbf['total_float_yellow'].set_bottom()
        wbf['total_float_yellow'].set_left()
        wbf['total_float_yellow'].set_right()

        wbf['total_number_yellow'] = workbook.add_format(
            {'align': 'right', 'bg_color': colors['yellow'], 'bold': 1, 'num_format': '#,##0', 'font_name': 'Georgia'})
        wbf['total_number_yellow'].set_top()
        wbf['total_number_yellow'].set_bottom()
        wbf['total_number_yellow'].set_left()
        wbf['total_number_yellow'].set_right()

        wbf['total_yellow'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['yellow'], 'align': 'center', 'font_name': 'Georgia'})
        wbf['total_yellow'].set_left()
        wbf['total_yellow'].set_right()
        wbf['total_yellow'].set_top()
        wbf['total_yellow'].set_bottom()

        wbf['total_float_orange'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['orange'], 'align': 'right', 'num_format': '#,##0.00',
             'font_name': 'Georgia'})
        wbf['total_float_orange'].set_top()
        wbf['total_float_orange'].set_bottom()
        wbf['total_float_orange'].set_left()
        wbf['total_float_orange'].set_right()

        wbf['total_number_orange'] = workbook.add_format(
            {'align': 'right', 'bg_color': colors['orange'], 'bold': 1, 'num_format': '#,##0', 'font_name': 'Georgia'})
        wbf['total_number_orange'].set_top()
        wbf['total_number_orange'].set_bottom()
        wbf['total_number_orange'].set_left()
        wbf['total_number_orange'].set_right()

        wbf['total_orange'] = workbook.add_format(
            {'bold': 1, 'bg_color': colors['orange'], 'align': 'center', 'font_name': 'Georgia'})
        wbf['total_orange'].set_left()
        wbf['total_orange'].set_right()
        wbf['total_orange'].set_top()
        wbf['total_orange'].set_bottom()

        wbf['header_detail_space'] = workbook.add_format({'font_name': 'Georgia'})
        wbf['header_detail_space'].set_left()
        wbf['header_detail_space'].set_right()
        wbf['header_detail_space'].set_top()
        wbf['header_detail_space'].set_bottom()

        wbf['header_detail'] = workbook.add_format({'bg_color': '#E0FFC2', 'font_name': 'Georgia'})
        wbf['header_detail'].set_left()
        wbf['header_detail'].set_right()
        wbf['header_detail'].set_top()
        wbf['header_detail'].set_bottom()

        return wbf, workbook






class AccountingReport(models.TransientModel):
    _inherit = "accounting.report"

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