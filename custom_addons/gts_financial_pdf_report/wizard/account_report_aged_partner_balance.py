# -*- coding: utf-8 -*-

import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import get_lang
import time
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero
from datetime import datetime
from dateutil.relativedelta import relativedelta
import xlsxwriter
import base64
from odoo import fields, models, api
from io import BytesIO
from odoo.tools import xlsxwriter
from datetime import datetime
from pytz import timezone
import pytz


class AccountAgedTrialBalance(models.TransientModel):

    _name = 'account.aged.trial.balance'
    _inherit = 'account.common.partner.report'
    _description = 'Account Aged Trial balance Report'

    period_length = fields.Integer(string='Period Length (days)', required=True, default=30)
    journal_ids = fields.Many2many('account.journal', string='Journals', required=True)
    date_from = fields.Date(default=lambda *a: time.strftime('%Y-%m-%d'))
    # branch_ids = fields.Many2many(string='Branch')
    # branch_ids = fields.Many2many('res.branch', 'account_aged_partner_balance_branch_rel',
    #                               'account_aged_partner_balance_id',
    #                               'branch_id', 'Branches')
    datas = fields.Binary('File', readonly=True)
    datas_fname = fields.Char('Filename', readonly=True)
    partner_ids=fields.Many2many('res.partner', string="Partner")

    # for excel report purpose
    def _get_partner_move_lines(self, account_type, date_from, target_move, period_length,selected_partner_ids, data):
        # This method can receive the context key 'include_nullified_amount' {Boolean}
        # Do an invoice and a payment and unreconcile. The amount will be nullified
        # By default, the partner wouldn't appear in this report.
        # The context key allow it to appear
        # In case of a period_length of 30 days as of 2019-02-08, we want the following periods:
        # Name       Stop         Start
        # 1 - 30   : 2019-02-07 - 2019-01-09
        # 31 - 60  : 2019-01-08 - 2018-12-10
        # 61 - 90  : 2018-12-09 - 2018-11-10
        # 91 - 120 : 2018-11-09 - 2018-10-11
        # +120     : 2018-10-10
        print('now data is',data)
        print('branch is',data['form']['branch_ids'])
        get_branch_ids = data['form']['branch_ids']

        # get_branch_ids = []
        where_branch_ids = "1" \
                           "" \
                           "" \
                           "" \
                           "" \
                           "" \
                           "=1"
        # print('here the branch ids', branch_ids)
        # if branch_ids:
        #     where_branch_ids = " l.branch_id in %s" % str(tuple(branch_ids)).replace(',)',')')  # create a tuple and remove comma
        #     print('where branch ids', where_branch_ids)
        #     for id in branch_ids:
        #         if id != "":
        #             get_branch_ids.append(int(id))
        print('get branch ids', get_branch_ids)

        if len(get_branch_ids) == 1:
            where_branch_ids = "l.branch_id = {}".format(get_branch_ids[0])
            print('second where branch ids', where_branch_ids)
        if len(get_branch_ids) > 1:
            where_branch_ids = "l.branch_id in {}".format(tuple(get_branch_ids))
            print('third branch id',where_branch_ids)

        ctx = self._context
        periods = {}
        date_from = fields.Date.from_string(date_from)
        start = date_from - relativedelta(days=1)
        for i in range(5)[::-1]:
            stop = start - relativedelta(days=period_length)
            period_name = str((5-(i+1)) * period_length + 1) + '-' + str((5-i) * period_length)
            period_stop = (start - relativedelta(days=1)).strftime('%Y-%m-%d')
            if i == 0:
                period_name = '+' + str(4 * period_length)
            periods[str(i)] = {
                'name': period_name,
                'stop': period_stop,
                'start': (i!=0 and stop.strftime('%Y-%m-%d') or False),
            }
            start = stop

        res = []
        total = []
        partner_clause = ''
        cr = self.env.cr
        user_company = self.env.user.company_id
        user_currency = user_company.currency_id
        company_ids = self._context.get('company_ids') or [user_company.id]
        move_state = ['draft', 'posted']
        if target_move == 'posted':
            move_state = ['posted']
        arg_list = (tuple(move_state), tuple(account_type))
        #build the reconciliation clause to see what partner needs to be printed
        reconciliation_clause = '(l.reconciled IS FALSE)'
        cr.execute('SELECT debit_move_id, credit_move_id FROM account_partial_reconcile where max_date > %s', (date_from,))
        reconciled_after_date = []
        for row in cr.fetchall():
            reconciled_after_date += [row[0], row[1]]
        if reconciled_after_date:
            reconciliation_clause = '(l.reconciled IS FALSE OR l.id IN %s)'
            arg_list += (tuple(reconciled_after_date),)
        if ctx.get('partner_ids'):
            partner_clause = 'AND (l.partner_id IN %s)'
            arg_list += (tuple(ctx['partner_ids'].ids),)
        if ctx.get('partner_categories'):
            partner_clause += 'AND (l.partner_id IN %s)'
            partner_ids = self.env['res.partner'].search([('category_id', 'in', ctx['partner_categories'].ids)]).ids
            arg_list += (tuple(partner_ids or [0]),)
        arg_list += (date_from, tuple(company_ids))
        query = '''
            SELECT DISTINCT l.partner_id, UPPER(res_partner.name), rb.name
            FROM account_move_line AS l left join res_partner on l.partner_id = res_partner.id, account_account, account_move am,
            res_branch rb
            WHERE (l.account_id = account_account.id)
                AND (l.move_id = am.id)
                AND (l.branch_id = rb.id)
                AND (am.state IN %s)
                AND (account_account.internal_type IN %s)
                AND ''' + reconciliation_clause + partner_clause + '''
                AND (l.date <= %s)
                AND l.company_id IN %s and {}
            ORDER BY UPPER(res_partner.name)'''.format(where_branch_ids)   # 'where_branch_ids' using for filtering
        cr.execute(query, arg_list)

        partners = cr.dictfetchall()
        print('partners',partners)
        # for partner in partners:
        #     print('partners branch', partner['name'])
        # put a total of 0
        for i in range(7):
            total.append(0)

        # Build a string like (1,2,3) for easy use in SQL query
        partner_ids = [partner['partner_id'] for partner in partners if partner['partner_id']]
        selected_partner = []
        if len(selected_partner_ids.ids) > 0:
            for selective in selected_partner_ids.ids:
                for all in partner_ids:
                    if selective == all:
                        selected_partner.append(selective)
            partner_ids.clear()
            partner_ids = selected_partner
        lines = dict((partner['partner_id'] or False, []) for partner in partners)
        if not partner_ids:
            return [], [], {}

        # Use one query per period and store results in history (a list variable)
        # Each history will contain: history[1] = {'<partner_id>': <partner_debit-credit>}
        history = []
        for i in range(5):
            args_list = (tuple(move_state), tuple(account_type), tuple(partner_ids),)
            dates_query = '(COALESCE(l.date_maturity,l.date)'

            if periods[str(i)]['start'] and periods[str(i)]['stop']:
                dates_query += ' BETWEEN %s AND %s)'
                args_list += (periods[str(i)]['start'], periods[str(i)]['stop'])
            elif periods[str(i)]['start']:
                dates_query += ' >= %s)'
                args_list += (periods[str(i)]['start'],)
            else:
                dates_query += ' <= %s)'
                args_list += (periods[str(i)]['stop'],)
            args_list += (date_from, tuple(company_ids))

            query = '''SELECT l.id
                    FROM account_move_line AS l, account_account, account_move am
                    WHERE (l.account_id = account_account.id) AND (l.move_id = am.id)
                        AND (am.state IN %s)
                        AND (account_account.internal_type IN %s)
                        AND ((l.partner_id IN %s) OR (l.partner_id IS NULL))
                        AND ''' + dates_query + '''
                    AND (l.date <= %s)
                    AND l.company_id IN %s
                    ORDER BY COALESCE(l.date_maturity, l.date)'''
            cr.execute(query, args_list)
            partners_amount = {}
            aml_ids = cr.fetchall()
            aml_ids = aml_ids and [x[0] for x in aml_ids] or []
            for line in self.env['account.move.line'].browse(aml_ids).with_context(prefetch_fields=False):
                partner_id = line.partner_id.id or False
                if partner_id not in partners_amount:
                    partners_amount[partner_id] = 0.0
                line_amount = line.company_id.currency_id._convert(line.balance, user_currency, user_company, date_from)
                if user_currency.is_zero(line_amount):
                    continue
                for partial_line in line.matched_debit_ids:
                    if partial_line.max_date <= date_from:
                        line_amount += partial_line.company_id.currency_id._convert(partial_line.amount, user_currency, user_company, date_from)
                for partial_line in line.matched_credit_ids:
                    if partial_line.max_date <= date_from:
                        line_amount -= partial_line.company_id.currency_id._convert(partial_line.amount, user_currency, user_company, date_from)

                if not self.env.user.company_id.currency_id.is_zero(line_amount):
                    partners_amount[partner_id] += line_amount
                    lines[partner_id].append({
                        'line': line,
                        'amount': line_amount,
                        'period': i + 1,
                        })
            history.append(partners_amount)

        # This dictionary will store the not due amount of all partners
        undue_amounts = {}
        query = '''SELECT l.id
                FROM account_move_line AS l, account_account, account_move am
                WHERE (l.account_id = account_account.id) AND (l.move_id = am.id)
                    AND (am.state IN %s)
                    AND (account_account.internal_type IN %s)
                    AND (COALESCE(l.date_maturity,l.date) >= %s)\
                    AND ((l.partner_id IN %s) OR (l.partner_id IS NULL))
                AND (l.date <= %s)
                AND l.company_id IN %s
                ORDER BY COALESCE(l.date_maturity, l.date)'''
        cr.execute(query, (tuple(move_state), tuple(account_type), date_from, tuple(partner_ids), date_from, tuple(company_ids)))
        aml_ids = cr.fetchall()
        aml_ids = aml_ids and [x[0] for x in aml_ids] or []
        for line in self.env['account.move.line'].browse(aml_ids):
            partner_id = line.partner_id.id or False
            if partner_id not in undue_amounts:
                undue_amounts[partner_id] = 0.0
            line_amount = line.company_id.currency_id._convert(line.balance, user_currency, user_company, date_from)
            if user_currency.is_zero(line_amount):
                continue
            for partial_line in line.matched_debit_ids:
                if partial_line.max_date <= date_from:
                    line_amount += partial_line.company_id.currency_id._convert(partial_line.amount, user_currency, user_company, date_from)
            for partial_line in line.matched_credit_ids:
                if partial_line.max_date <= date_from:
                    line_amount -= partial_line.company_id.currency_id._convert(partial_line.amount, user_currency, user_company, date_from)
            if not self.env.user.company_id.currency_id.is_zero(line_amount):
                undue_amounts[partner_id] += line_amount
                lines[partner_id].append({
                    'line': line,
                    'amount': line_amount,
                    'period': 6,
                })

        for partner in partners:
            print('partner',partner)
            if partner['partner_id'] is None:
                partner['partner_id'] = False
            at_least_one_amount = False
            values = {}
            undue_amt = 0.0
            if partner['partner_id'] in undue_amounts:  # Making sure this partner actually was found by the query
                undue_amt = undue_amounts[partner['partner_id']]

            total[6] = total[6] + undue_amt
            values['direction'] = undue_amt
            if not float_is_zero(values['direction'], precision_rounding=self.env.user.company_id.currency_id.rounding):
                at_least_one_amount = True

            for i in range(5):
                during = False
                if partner['partner_id'] in history[i]:
                    during = [history[i][partner['partner_id']]]
                # Adding counter
                total[(i)] = total[(i)] + (during and during[0] or 0)
                values[str(i)] = during and during[0] or 0.0
                if not float_is_zero(values[str(i)], precision_rounding=self.env.user.company_id.currency_id.rounding):
                    at_least_one_amount = True
            values['total'] = sum([values['direction']] + [values[str(i)] for i in range(5)])
            ## Add for total
            total[(i + 1)] += values['total']
            values['partner_id'] = partner['partner_id']
            if partner['partner_id']:
                browsed_partner = self.env['res.partner'].browse(partner['partner_id'])
                print('browsed partner',browsed_partner)
                values['name'] = browsed_partner.name and len(browsed_partner.name) >= 45 and browsed_partner.name[0:40] + '...' or browsed_partner.name
                print('values[name]',values['name'])
                values['trust'] = browsed_partner.trust
                print('values[trust]', values['trust'])

            else:
                values['name'] = _('Unknown Partner')
                values['trust'] = False

            if at_least_one_amount or (self._context.get('include_nullified_amount') and lines[partner['partner_id']]):
                res.append(values)

            if partner['name']:
                values['branch_name'] = partner['name']
            else:
                values['branch_name'] = '-'
            print('values[branch_name]',values['branch_name'])
            print('res now is',res)

        return res, total, lines


    def _print_report(self, data): # this method is override from a function in 'account.common.report'
        res = {}
        data = self.pre_print_report(data)
        data['form'].update(self.read(['period_length'])[0])
        data['form'].update(self.read(['branch_ids'])[0]) # update the dictionary as key is 'branch_ids'
        print('data',data)
        period_length = data['form']['period_length']
        if period_length<=0:
            raise UserError(_('You must set a period length greater than 0.'))
        if not data['form']['date_from']:
            raise UserError(_('You must set a start date.'))

        start = datetime.strptime(str(data['form']['date_from']), "%Y-%m-%d")

        for i in range(5)[::-1]:
            stop = start - relativedelta(days=period_length - 1)
            res[str(i)] = {
                'name': (i!=0 and (str((5-(i+1)) * period_length) + '-' + str((5-i) * period_length)) or ('+'+str(4 * period_length))),
                'stop': start.strftime('%Y-%m-%d'),
                'start': (i!=0 and stop.strftime('%Y-%m-%d') or False),
            }
            start = stop - relativedelta(days=1)
        data['form'].update(res)
        data['partner_ids']=self.partner_ids
        return self.env.ref('gts_financial_pdf_report.action_report_aged_partner_balance').with_context(landscape=True).report_action(self, data=data)

    def _build_contexts(self, data):
        result = {}
        print('yes build contexts')
        result['journal_ids'] = 'journal_ids' in data['form'] and data['form']['journal_ids'] or False
        result['state'] = 'target_move' in data['form'] and data['form']['target_move'] or ''
        result['date_from'] = data['form']['date_from'] or False
        result['date_to'] = data['form']['date_to'] or False
        result['strict_range'] = True if result['date_from'] else False
        result['company_id'] = data['form']['company_id'][0] or False
        return result

    def print_excel_report(self):
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(['date_from', 'date_to', 'journal_ids', 'target_move', 'company_id'])[0]
        used_context = self._build_contexts(data)
        print('used_context is',used_context)
        data['form']['used_context'] = dict(used_context, lang=get_lang(self.env).code)
        res = {}
        data = self.pre_print_report(data)
        data['form'].update(self.read(['period_length'])[0])
        data['form'].update(self.read(['branch_ids'])[0]) # update the dictionary as key is 'branch_ids'

        period_length = data['form']['period_length']
        if period_length <= 0:
            raise UserError(_('You must set a period length greater than 0.'))
        if not data['form']['date_from']:
            raise UserError(_('You must set a start date.'))

        start = datetime.strptime(str(data['form']['date_from']), "%Y-%m-%d")

        for i in range(5)[::-1]:
            stop = start - relativedelta(days=period_length - 1)
            res[str(i)] = {
                'name': (i != 0 and (str((5 - (i + 1)) * period_length) + '-' + str((5 - i) * period_length)) or (
                            '+' + str(4 * period_length))),
                'stop': start.strftime('%Y-%m-%d'),
                'start': (i != 0 and stop.strftime('%Y-%m-%d') or False),
            }
            start = stop - relativedelta(days=1)
        data['form'].update(res)
        print('now the data is',data)

        # if not data.get('form') or not self.env.context.get('active_model') or not self.env.context.get('active_id'):
        #     raise UserError(_("Form content is missing, this report cannot be printed."))

        total = []
        # model = self.env.context.get('active_model')
        # docs = self.env[model].browse(self.env.context.get('active_id'))

        target_move = data['form'].get('target_move', 'all')
        date_from = fields.Date.from_string(data['form'].get('date_from')) or fields.Date.today()

        if data['form']['result_selection'] == 'customer':
            print ('yes yes yes')
            account_type = ['receivable']
        elif data['form']['result_selection'] == 'supplier':
            account_type = ['payable']
        else:
            account_type = ['payable', 'receivable']
        partner_ids = self.partner_ids

        movelines, total, dummy = self._get_partner_move_lines(account_type, date_from, target_move, data['form']['period_length'],partner_ids, data)
        print('azhar checked')
        print('data -',data)
        print('get partner lines(movelines)',movelines)
        print('get directon(total)',total)
        # return {
        #     'doc_ids': self.ids,
        #     'doc_model': model,
        #     'data': data['form'],
        #     'docs': docs,
        #     'time': time,
        #     'get_partner_lines': movelines,
        #     'get_direction': total,
        #     'company_id': self.env['res.company'].browse(
        #         data['form']['company_id'][0]),
        # }
        report_name = 'Aged Partner Balance'
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
        worksheet.merge_range('A%s:B%s' % (row-1, row-1), 'Start Date',wbf['header_orange'])
        worksheet.merge_range('D%s:E%s' % (row-1,row-1), 'Period Length(days)',wbf['header_orange'])
        row += 1
        worksheet.merge_range('A%s:B%s' % (row-1,row-1), str(data['form']['date_from']))
        worksheet.merge_range('D%s:E%s' % (row-1,row-1), data['form']['period_length'])
        row += 1
        worksheet.merge_range('A%s:B%s' % (row-1,row-1),'Partner',wbf['header_orange'])
        worksheet.merge_range('D%s:E%s' % (row-1,row-1), 'Target Moves:',wbf['header_orange'])
        row += 1
        if data['form']['result_selection'] == 'customer':
            worksheet.merge_range('A%s:B%s' % (row-1,row-1),'Receivable Accounts')
        if data['form']['result_selection'] == 'supplier':
            worksheet.merge_range('A%s:B%s' % (row-1,row-1),'Payable Accounts')
        if data['form']['result_selection'] == 'customer_supplier':
            worksheet.merge_range('A%s:B%s' % (row-1,row-1),'Receivable and Payable Accounts')

        if data['form']['target_move'] == 'all':
            worksheet.merge_range('D%s:E%s' % (row-1,row-1), 'All Entries')
        if data['form']['target_move'] == 'posted':
            worksheet.merge_range('D%s:E%s' % (row-1, row-1),'All Posted Entries')
        row += 1
        col2 = 0
        # for product in column_product:
        #     column_name = product[0]
        #     column_width = product[1]
        #     worksheet.set_column(col2,col2,column_width)
        #     worksheet.write(row-2,col2,,wbf['total_orange'])
        #     col2 += 1
        worksheet.set_column(col2,col2,24)
        worksheet.write(row-2,col2,'Partners',wbf['header_orange'])
        col2 += 1
        worksheet.set_column(col2,col2,12)
        worksheet.write(row-2,col2,'Not due',wbf['header_orange'])
        col2 += 1
        worksheet.set_column(col2,col2,13)
        worksheet.write(row-2,col2,data['form']['4']['name'],wbf['header_orange'])
        col2 += 1
        worksheet.set_column(col2,col2,13)
        worksheet.write(row-2,col2,data['form']['3']['name'],wbf['header_orange'])
        col2 += 1
        worksheet.set_column(col2,col2,13)
        worksheet.write(row-2,col2,data['form']['2']['name'],wbf['header_orange'])
        col2 += 1
        worksheet.set_column(col2,col2,13)
        worksheet.write(row-2,col2,data['form']['1']['name'],wbf['header_orange'])
        col2 += 1
        worksheet.set_column(col2,col2,12)
        worksheet.write(row-2,col2,data['form']['0']['name'],wbf['header_orange'])
        col2 += 1
        worksheet.set_column(col2,col2,14)
        worksheet.write(row-2,col2,'Total',wbf['header_orange'])
        col2 += 1
        worksheet.set_column(col2,col2,25)
        worksheet.write(row-2,col2,'Branch',wbf['header_orange'])
        row += 1

        col3 = 0
        if movelines:
            worksheet.write(row-2,col3,'Account Total',wbf['header_detail'])
            col3 += 1
            worksheet.write(row-2,col3,total[6],wbf['header_detail'])
            col3 += 1
            worksheet.write(row-2,col3,total[4],wbf['header_detail'])
            col3 += 1
            worksheet.write(row-2,col3,total[3],wbf['header_detail'])
            col3 += 1
            worksheet.write(row-2,col3,total[2],wbf['header_detail'])
            col3 += 1
            worksheet.write(row-2,col3,total[1],wbf['header_detail'])
            col3 += 1
            worksheet.write(row-2,col3,total[0],wbf['header_detail'])
            col3 += 1
            worksheet.write(row-2,col3,total[5],wbf['header_detail'])
            row += 1

        for partner in movelines:
            col4 = 0
            worksheet.write(row-2,col4,partner['name'])
            col4 += 1
            worksheet.write(row-2,col4,partner['direction'])
            col4 += 1
            worksheet.write(row-2,col4,partner['4'])
            col4 += 1
            worksheet.write(row-2,col4,partner['3'])
            col4 += 1
            worksheet.write(row-2,col4,partner['2'])
            col4 += 1
            worksheet.write(row-2,col4,partner['1'])
            col4 += 1
            worksheet.write(row-2,col4,partner['0'])
            col4 += 1
            worksheet.write(row-2,col4,partner['total'])
            col4 += 1
            worksheet.write(row-2,col4,partner['branch_name'])
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



# class AccountAgedTrialBalanceInherit(models.TransientModel):
#     _inherit = 'account.aged.trial.balance'
#
#     branch_ids = fields.Many2many('res.branch', string='Branch')
    # branch_ids = fields.Many2many('res.branch', 'account_aged_partner_balance_branch_rel',
    #                               'account_aged_partner_balance_id',
    #                               'branch_id', 'Branches') # set the table name which is 'account_aged_partner_balance_branch_rel', and set the attribute is 'account_aged_partner_balance_id' and 'branch_id'

