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
from datetime import date, datetime, timedelta
from datetime import timedelta, datetime
import json
from datetime import datetime, timedelta

from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DATE_FORMAT
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DATETIME_FORMAT, BytesIO, xlsxwriter, base64
import xlsxwriter
import base64
from odoo import fields, models, api
from io import BytesIO
from datetime import datetime
from odoo import models, fields


class DayBookWizard(models.TransientModel):
    _inherit = "account.common.account.report"
    _name = 'account.day.book.report'
    _description = 'Account Day Book Report'

    company_id = fields.Many2one('res.company', string='Company', domain=lambda self:self._get_companies(),default=lambda self: self.env.user.company_id,required=True)
    journal_ids = fields.Many2many('account.journal', string='Journals',
                                   required=True,
                                   default=lambda self: self.env[
                                       'account.journal'].search([]))
    target_move = fields.Selection([('posted', 'All Posted Entries'),
                                    ('all', 'All Entries')], string='Target Moves', required=True,
                                   default='posted')

    account_ids = fields.Many2many('account.account',
                                   'account_report_daybook_account_rel',
                                   'report_id', 'account_id',
                                   'Accounts')

    date_from = fields.Date(string='Start Date', default=date.today(),
                            requred=True)
    date_to = fields.Date(string='End Date', default=date.today(),
                          requred=True)
    branch_ids = fields.Many2one('res.branch', string='Branch')
    datas = fields.Binary('File', readonly=True)
    datas_fname = fields.Char('Filename', readonly=True)

    def _get_companies(self):
        query = """select * from res_company_users_rel where user_id={}""".format(self.env.user.id)
        self._cr.execute(query=query)
        allowed_companies = self._cr.fetchall()
        allowed_company = []
        for company in allowed_companies:
            allowed_company.append(company[0])
        return [('id', 'in', allowed_company)]

    def _build_contexts(self, data):
        result = {}
        result['journal_ids'] = 'journal_ids' in data['form'] and data['form'][
            'journal_ids'] or False
        result['state'] = 'target_move' in data['form'] and data['form'][
            'target_move'] or ''
        result['date_from'] = data['form']['date_from'] or False
        result['date_to'] = data['form']['date_to'] or False
        result['strict_range'] = True if result['date_from'] else False
        if data['form']['branch_ids'] :
            result['branch_ids'] = 'branch_ids' in data['form'] and data['form']['branch_ids'][0] or False
        result['company_id'] = data['form']['company_id'][0]
        print('the result is',result)
        return result

    def check_report(self):
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = \
        self.read(['date_from', 'date_to', 'journal_ids', 'target_move',
                   'account_ids','branch_ids','company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = dict(used_context,
                                            lang=self.env.context.get(
                                                'lang') or 'en_US')
        print('data is',data)
        return self.env.ref(
            'gts_financial_pdf_report.day_book_pdf_report').report_action(self, data=data)

    def _get_account_move_entry(self, accounts, form_data, pass_date):
        cr = self.env.cr
        context = dict(self._context or {})
        move_line = self.env['account.move.line']
        tables, where_clause, where_params = move_line._query_get()
        wheres = [""]
        if where_clause.strip():
            wheres.append(where_clause.strip())
        if form_data['target_move'] == 'posted':
            target_move = "AND m.state = 'posted'"
            if context.get('branch_ids'):
                target_move = "AND m.state = 'posted' AND l.branch_id =" + str(context['branch_ids'])
        else:
            target_move = ''
        sql = ('''
                SELECT l.id AS lid, acc.name as accname, l.account_id AS account_id, to_char(l.date, 'dd/mm/yyyy') AS ldate, j.code AS lcode, l.currency_id, 
                l.amount_currency, l.ref AS lref, l.name AS lname, COALESCE(l.debit,0) AS debit, COALESCE(l.credit,0) AS credit, 
                COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit), 0) AS balance,
                m.name AS move_name, c.symbol AS currency_code, p.name AS partner_name
                FROM account_move_line l
                JOIN account_move m ON (l.move_id=m.id)
                LEFT JOIN res_currency c ON (l.currency_id=c.id)
                LEFT JOIN res_partner p ON (l.partner_id=p.id)
                JOIN account_journal j ON (l.journal_id=j.id)
                JOIN account_account acc ON (l.account_id = acc.id) 
                WHERE m.state != 'cancel' and l.account_id IN %s AND l.journal_id IN %s ''' + target_move + ''' AND l.date = %s
                GROUP BY l.id, l.account_id, l.date,
                     j.code, l.currency_id, l.amount_currency, l.ref, l.name, m.name, c.symbol, p.name , acc.name
                     ORDER BY l.date DESC
        ''')
        params = (
        tuple(accounts.ids), tuple(form_data['journal_ids']), pass_date)
        cr.execute(sql, params)
        data = cr.dictfetchall()
        res = {}
        debit = credit = balance = 0.00
        for line in data:
            debit += line['debit']
            credit += line['credit']
            balance += line['balance']
        res['debit'] = debit
        res['credit'] = credit
        res['balance'] = balance
        res['lines'] = data
        return res

    def print_excel_report(self):
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = \
            self.read(['date_from', 'date_to', 'journal_ids', 'target_move',
                       'account_ids', 'branch_ids', 'company_id'])[0] # take current things from wizard
        used_context = self._build_contexts(data) # call the '_build_context' function
        data['form']['used_context'] = dict(used_context,
                                            lang=self.env.context.get(
                                                'lang') or 'en_US') # create another dictionary inside data dictionary 'form' key value which's key value is 'used_context'
        print('data is', data)

        self.model = self.env.context.get('active_model')
        # docs = self.env[self.model].browse(
        #     self.env.context.get('active_ids', []))
        form_data = data['form']
        codes = []
        if data['form'].get('journal_ids', False):
            codes = [journal.code for journal in
                     self.env['account.journal'].search(
                         [('id', 'in', data['form']['journal_ids'])])]
        active_acc = data['form']['account_ids']
        accounts = self.env['account.account'].search(
            [('id', 'in', active_acc)]) if data['form']['account_ids'] else \
            self.env['account.account'].search([])

        # date_start = datetime.strptime(form_data['date_from'],
        #                                '%Y-%m-%d').date()
        # print('date_start is', date_start)
        # date_end = datetime.strptime(form_data['date_to'], '%Y-%m-%d').date()
        # print('date_end is', date_end)
        date_start = self.date_from
        date_end = self.date_to

        days = (date_end - date_start).days
        print('days is ',days)
        dates = []
        record = []
        for i in range(days + 1):
            dates.append(date_start + timedelta(days=i)) # create a list with all dates
        for head in dates:
            pass_date = str(head)
            accounts_res = self.with_context(
                data['form'].get('used_context', {}))._get_account_move_entry(
                accounts, form_data, pass_date)
            if accounts_res['lines']:
                record.append({
                    'date': head.strftime('%d/%m/%Y'),
                    'debit': accounts_res['debit'],
                    'credit': accounts_res['credit'],
                    'balance': accounts_res['balance'],
                    'child_lines': accounts_res['lines']
                })
        print('final record is', record)
        all_journals = ""
        comma = ","
        ck = 0
        for jrnl in codes:
            ck += 1
            print('jrnl is', jrnl)
            all_journals += jrnl
            if ck != len(codes):
                all_journals += comma
        print('all journals are', all_journals)


        report_name = 'Account Day Book Report'
        filename = '%s' % (report_name)
        fp = BytesIO()
        workbook = xlsxwriter.Workbook(fp)
        wbf, workbook = self.add_workbook_format(workbook)
        worksheet = workbook.add_worksheet(report_name)
        worksheet.merge_range('A2:I3', report_name, wbf['title_doc'])

        Journal_column = [
            ('Journal_name',70,'char','char')
        ]
        Target_column = [
            ('Target_name',50,'char','char')
        ]
        Column_product = [
            ('Date',15,'char','char'),
            ('JRNL',10,'char','char'),
            ('Partner',14,'char','char'),
            ('Ref',8,'char','char'),
            ('Move',18,'char','char'),
            ('Entry Lable',30,'char','char'),
            ('Debit',13,'float','float'),
            ('Credit',14,'float','float'),
            ('Balance',20,'float','float')
        ]
        row = 5
        journal_name = Journal_column[0][0]
        journal_width = Journal_column[0][1]
        worksheet.set_column(0,0,journal_width)
        # worksheet.write(row-1, 0,journal_name,wbf['header_orange'])
        print('record is',record)
        print('codes is',codes)
        print('total codes are:')

        col2 = 1
        target_name = Target_column[0][0]
        # target_width = Target_column[0][1]
        # worksheet.set_column(0, 0, target_width)
        # worksheet.write(row - 1, 0, target_name, wbf['header_orange'])
        #
        # worksheet.write(row - 1, 1, data['form']['target_move'])

        # worksheet.write(row-1,col2,all_journals)
        worksheet.merge_range('A5:D5',journal_name ,wbf['header_detail'])
        worksheet.merge_range('H5:I5',target_name ,wbf['header_detail'])

        row += 1
        worksheet.merge_range('A6:F6', all_journals,wbf['header_detail'])
        worksheet.merge_range('H6:I6', data['form']['target_move'],wbf['header_detail'])

        # worksheet.merge_range('A%s:B%s' % (row, row), 'Grand Total', wbf['total_orange'])
        # worksheet.write(row-1,col2,all_journals)

        row += 1

        # worksheet.write(row-1,col2,all_journals)
        # col2 += 1
        # row += 1


        # row += 1

        col3 = 0
        for prod in Column_product: # for header
            column_name1 = prod[0]
            column_width1 = prod[1]
            column_type = prod[2]
            worksheet.set_column(col3, col3, column_width1)
            worksheet.write(row - 1, col3, column_name1, wbf['header_orange'])
            col3 += 1
        row += 1

        for item in record:
            col4 = 0
            worksheet.write(row - 1, col4, str(item['date']),wbf['header_yellow'])
            col4 += 6
            worksheet.write(row - 1, col4, item['debit'],wbf['header_yellow'])
            col4 += 1
            worksheet.write(row - 1, col4, item['credit'],wbf['header_yellow'])
            col4 += 1
            worksheet.write(row - 1, col4, item['balance'],wbf['header_yellow'])
            row += 1
            for line in item['child_lines']:
                col5 = 0
                worksheet.write(row - 1, col5, str(line['ldate']))
                col5 += 1
                worksheet.write(row - 1, col5, line['lcode'])
                col5 += 1
                worksheet.write(row - 1, col5, line['partner_name'])
                col5 += 1
                worksheet.write(row - 1, col5, line['lref'])
                col5 += 1
                worksheet.write(row - 1, col5, line['move_name'])
                col5 += 1
                worksheet.write(row - 1, col5, line['lname'])
                col5 += 1
                worksheet.write(row - 1, col5, line['debit'])
                col5 += 1
                worksheet.write(row - 1, col5, line['credit'])
                col5 += 1
                worksheet.write(row - 1, col5, line['balance'])

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

        # return {
        #     'doc_model': self.model,
        #     'data': data['form'],
        #     # 'docs': docs,
        #     'Accounts': record,
        #     'print_journal': codes,
        # }

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






