# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.tools import get_lang
from odoo import api, fields, models
from odoo.tools import get_lang
from datetime import datetime, timedelta
from odoo import models, fields
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DATE_FORMAT
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DATETIME_FORMAT, BytesIO, xlsxwriter, base64
from odoo import fields, models
import xlsxwriter
import base64
from odoo import fields, models, api
from io import BytesIO
from datetime import datetime
from pytz import timezone
import pytz


class AccountPrintJournal(models.TransientModel):
    _inherit = "account.common.journal.report"
    _name = "account.print.journal"
    _description = "Account Print Journal"

    sort_selection = fields.Selection([('date', 'Date'), ('move_name', 'Journal Entry Number'),], 'Entries Sorted by', required=True, default='move_name')
    journal_ids = fields.Many2many('account.journal', string='Journals', required=True, default=lambda self: self.env['account.journal'].search([('type', 'in', ['sale', 'purchase'])]))
    datas = fields.Binary('File', readonly=True)
    datas_fname = fields.Char('Filename', readonly=True)

    def _get_query_get_clause(self, data):
        return self.env['account.move.line'].with_context(data['form'].get('used_context', {}))._query_get()

    def _get_taxes(self, data, journal_id):
        move_state = ['draft', 'posted']
        if data['form'].get('target_move', 'all') == 'posted':
            move_state = ['posted']

        query_get_clause = self._get_query_get_clause(data)
        params = [tuple(move_state), tuple(journal_id.ids)] + query_get_clause[2]
        query = """
            SELECT rel.account_tax_id, SUM("account_move_line".balance) AS base_amount
            FROM account_move_line_account_tax_rel rel, """ + query_get_clause[0] + """ 
            LEFT JOIN account_move am ON "account_move_line".move_id = am.id
            WHERE "account_move_line".id = rel.account_move_line_id
                AND am.state IN %s
                AND "account_move_line".journal_id IN %s
                AND """ + query_get_clause[1] + """
           GROUP BY rel.account_tax_id"""
        self.env.cr.execute(query, tuple(params))
        ids = []
        base_amounts = {}
        for row in self.env.cr.fetchall():
            ids.append(row[0])
            base_amounts[row[0]] = row[1]

        res = {}
        for tax in self.env['account.tax'].browse(ids):
            self.env.cr.execute('SELECT sum(debit - credit) FROM ' + query_get_clause[0] + ', account_move am '
                'WHERE "account_move_line".move_id=am.id AND am.state IN %s AND "account_move_line".journal_id IN %s AND ' + query_get_clause[1] + ' AND tax_line_id = %s',
                tuple(params + [tax.id]))
            res[tax] = {
                'base_amount': base_amounts[tax.id],
                'tax_amount': self.env.cr.fetchone()[0] or 0.0,
            }
            if journal_id.type == 'sale':
                #sales operation are credits
                res[tax]['base_amount'] = res[tax]['base_amount'] * -1
                res[tax]['tax_amount'] = res[tax]['tax_amount'] * -1
        return res

    def lines(self, target_move, journal_ids, sort_selection, data):
        if isinstance(journal_ids, int):
            journal_ids = [journal_ids]

        move_state = ['draft', 'posted']
        if target_move == 'posted':
            move_state = ['posted']

        query_get_clause = self._get_query_get_clause(data)
        params = [tuple(move_state), tuple(journal_ids)] + query_get_clause[2]
        query = 'SELECT "account_move_line".id FROM ' + query_get_clause[0] + ', account_move am, account_account acc WHERE "account_move_line".account_id = acc.id AND "account_move_line".move_id=am.id AND am.state IN %s AND "account_move_line".journal_id IN %s AND ' + query_get_clause[1] + ' ORDER BY '
        if sort_selection == 'date':
            query += '"account_move_line".date'
        else:
            query += 'am.name'
        query += ', "account_move_line".move_id, acc.code'
        self.env.cr.execute(query, tuple(params))
        ids = (x[0] for x in self.env.cr.fetchall())
        return self.env['account.move.line'].browse(ids)

    def _print_report(self, data):
        data = self.pre_print_report(data)
        data['form'].update({'sort_selection': self.sort_selection})
        return self.env.ref('account.action_report_journal').with_context(landscape=True).report_action(self, data=data)

    def print_excel_report(self):
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(['date_from', 'date_to', 'journal_ids', 'target_move', 'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = dict(used_context, lang=get_lang(self.env).code)

        data = self.pre_print_report(data)
        data['form'].update({'sort_selection': self.sort_selection})
        print('The ultimate data is', data)
        print('yes laste dukse')

        target_move = data['form'].get('target_move', 'all')
        sort_selection = data['form'].get('sort_selection', 'date')

        res = {}
        for journal in data['form']['journal_ids']:
            res[journal] = self.with_context(data['form'].get('used_context', {})).lines(target_move, journal, sort_selection, data)
        docs = self.env['account.journal'].browse(data['form']['journal_ids'])
        print('the last docs are',docs)
        print('the last data are',data)
        print('doc ids are',data['form']['journal_ids'])
        print('final final data is',data)
        print('now docs is',docs)
        print('lines are',res)
        # return {
        #     'doc_ids': data['form']['journal_ids'],
        #     'doc_model': self.env['account.journal'],
        #     'data': data,
        #     'docs': self.env['account.journal'].browse(data['form']['journal_ids']),
        #     'time': time,
        #     'lines': res,
        #     'sum_credit': self._sum_credit,
        #     'sum_debit': self._sum_debit,
        #     'get_taxes': self._get_taxes,
        #     'company_id': self.env['res.company'].browse(
        #         data['form']['company_id'][0]),
        # }

        report_name = 'Sale/Purchase Journal Report'
        filename = '%s' % (report_name)

        fp = BytesIO()
        workbook = xlsxwriter.Workbook(fp)
        wbf, workbook = self.add_workbook_format(workbook)
        worksheet = workbook.add_worksheet(report_name)
        worksheet.merge_range('A2:I3', report_name, wbf['title_doc'])

        column_product = [
            ('Move',20,'char','char'),
            ('Date',13,'char','char'),
            ('Account',13,'float','float'),
            ('Partner',21,'char','char'),
            ('Label',39,'char','char'),
            ('Debit',10,'float','float'),
            ('Credit',10,'float','float')
        ]
        tax_declaration = [
            ('Name',20,'char','char'),
            ('Base Amount',14,'float','float'),
            ('Tax Amount',14,'float','float')
        ]
        row = 5
        # worksheet.merge_range('A4:B4',)
        for doc in docs:
            worksheet.merge_range('A%s:E%s' % (row - 1, row - 1),doc.name + ' Journal', wbf['header_orange']) # after 'merge_range' automatically a new row created
            # worksheet.merge_range('D%s:E%s' % (row - 1, row - 1),'Journal', wbf['header_orange'])
            worksheet.write(row - 1, 3, 'Branch',wbf['header_orange'])
            worksheet.write(row-1,4,'Target Moves',wbf['header_orange'])

            row += 1

            worksheet.merge_range('A%s:B%s' % (row - 1, row - 1), 'Company', wbf['header_orange'])
            # worksheet.merge_range('D%s:E%s' % (row - 1, row - 1), 'Branch', wbf['header_orange'])

            # worksheet.merge_range('G%s:I%s' % (row - 1, row - 1), 'Journal', wbf['header_orange'])
            worksheet.merge_range('F%s:H%s' % (row - 1, row - 1), 'Entries Sorted By', wbf['header_orange'])
            # worksheet.merge_range('J%s:K%s' % (row - 1, row - 1), 'Target Moves', wbf['header_orange'])
            worksheet.write(row-1,3,data['form']['used_context']['branch_ids'])
            if data['form']['target_move'] == 'all':
                worksheet.write(row-1,4,'All Entries')
                # worksheet.merge_range('J%s:K%s' % (row - 1, row - 1), 'All Entries', wbf['header_orange'])
            if data['form']['target_move'] == 'posted':
                worksheet.write(row-1,4,'All Posted Entries')
                # worksheet.merge_range('J%s:K%s' % (row - 1, row - 1), 'All Posted Entries', wbf['header_orange'])

            row += 1

            worksheet.merge_range('A%s:B%s' % (row - 1, row - 1), data['form']['company_id'][1])
            # worksheet.merge_range('D%s:E%s' % (row - 1, row - 1), data['form']['used_context']['branch_ids'], wbf['header_orange'])
            # worksheet.merge_range('G%s:I%s' % (row - 1, row - 1), doc.name, wbf['header_orange'])

            if data['form']['sort_selection'] == 'move_name':
                worksheet.merge_range('F%s:H%s' % (row - 1, row - 1), 'Journal Entry Number')
            if data['form']['sort_selection'] == 'date':
                worksheet.merge_range('F%s:H%s' % (row - 1, row - 1), 'Date')

            row += 1 # after using merge range the row is automatically added by 1,if we add row by one then we have to use 'row-2' in header
            col3 = 0
            for product in column_product:
                column_name = product[0]
                column_width = product[1]
                worksheet.set_column(col3,col3,column_width)
                worksheet.write(row-2,col3,column_name,wbf['total_orange'])
                col3 += 1
            row += 1

            for aml in res[doc.id]: # 'res' is dictionary,'doc' is a key of dictionary which is object,so we want to access 'id' of object
                col4 = 0
                worksheet.write(row-2,col4,aml.move_id.name) # each id of object has many fields(like name,date etc) on db
                col4 += 1
                worksheet.write(row-2,col4,aml.date)
                col4 += 1
                worksheet.write(row-2,col4,aml.account_id.code)
                col4 += 1
                if aml.partner_id.name:
                    worksheet.write(row-2,col4,aml.partner_id.name)
                else:
                    worksheet.write(row - 2, col4, '')
                col4 += 1
                worksheet.write(row-2,col4,aml.name)
                col4 += 1
                worksheet.write(row-2,col4,aml.debit)
                col4 += 1
                worksheet.write(row-2,col4,aml.credit)
                row += 1
            # row += 1
            col5 = 0
            for tax_header in tax_declaration: # for header purpose
                header_name = tax_header[0]
                header_width = tax_header[1]
                worksheet.set_column(col5,col5,header_width)
                worksheet.write(row-1,col5,header_name,wbf['header_orange'])
                col5 += 1
            row += 1
            get_taxes = self._get_taxes(data,doc)
            col6 = 0
            for tax in get_taxes:
                worksheet.write(row-1,col6,tax.name)
                col6 += 1
                worksheet.write(row-1,col6,get_taxes[tax]['base_amount'])
                col6 += 1
                worksheet.write(row-1,col6,get_taxes[tax]['tax_amount'])
            row += 3

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





        # return {
        #     'doc_ids': data['form']['journal_ids'],
        #     'doc_model': self.env['account.journal'],
        #     'data': data,
        #     'docs': self.env['account.journal'].browse(data['form']['journal_ids']),
        #     # 'time': time,
        #     'lines': res,
        #     'sum_credit': self._sum_credit,
        #     'sum_debit': self._sum_debit,
        #     'get_taxes': self._get_taxes,
        #     'company_id': self.env['res.company'].browse(
        #         data['form']['company_id'][0]),
        # }





class AccountCommonJournalReport(models.TransientModel):
    _inherit = "account.common.journal.report"

    branch_ids = fields.Many2one('res.branch', string='Branch')
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.user.company_id)

    # @api.onchange('company_id')
    # def _onchange_company_id(self):
    #     if self.company_id:
    #         get_branch = self.env.user.branch_ids.filtered(lambda line: line.company_id.id == self.company_id.id)
    #         return {'domain': {'branch_ids': [('id', 'in', get_branch.ids)]}}
    #
    #     get_branch = self.env['res.branch'].search(
    #         [('id', 'in', self.env.user.branch_ids.ids), ('company_id', '=', self.env.user.company_id.id)])
    #     return {'domain': {'branch_ids': [('id', 'in', get_branch.ids)]}}
