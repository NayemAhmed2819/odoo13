# -*- coding: utf-8 -*-

import time
from odoo import api, models, _
from odoo.exceptions import UserError


class ReportFinancial(models.AbstractModel):
    _name = 'report.gts_financial_pdf_report.report_financial'

    def _compute_account_balance(self, accounts,company_id):
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
                    #             from_date_condition = "aml.date::DATE >='" + data.get('date_from') + "'::DATE"
                    #         if data.get('date_to'):
                    #             to_date_condition = "aml.date::DATE <='" + data.get('date_to') + "'::DATE"
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
        company_id =data["company_id"][0]
        lines = []
        account_report = self.env['account.financial.report'].search([('id', '=', data['account_report_id'][0])])
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
                    #         from_date_condition = "aml.date::DATE >='" + data.get('date_from') + "'::DATE"
                    #     if data.get('date_to'):
                    #         to_date_condition = "aml.date::DATE <='" + data.get('date_to') + "'::DATE"
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

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form') or not self.env.context.get('active_model') or not self.env.context.get('active_id'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        self.model = self.env.context.get('active_model')
        docs = self.env[self.model].browse(self.env.context.get('active_id'))
        report_lines = self.get_account_lines(data.get('form'))

        query_buffer_stock = """
            select COALESCE(sum(COALESCE(sq.quantity, 0)*COALESCE(ip.value_float, 0)), 0) as total_buffer_stock_value from stock_quant as sq
                left join product_product as pp on pp.id = sq.product_id
                left join ir_property as ip on ip.res_id = 'product.template'||pp.product_tmpl_id
                where sq.location_id = 449"""
        self._cr.execute(query=query_buffer_stock)
        value = self._cr.fetchall()
        # for line in report_lines:
        #     if 'type' in line.keys() and 'name' in line.keys():
        #         if line['type'] == 'report' and line['name'] == 'Accounts Receivable':
        #             sum
        #             print("Accounts Receivable")
        #         elif line['type'] == 'account' and '101703' in line['name']:
        #             print("101703 Cheque In Hand")
        #         elif line['type'] == 'account' and '121000' in line['name']:
        #             print("121000 Account Receivable")
        if data['form']['with_buffer_stock']:
            cnt = 0
            for line in report_lines:
                cnt += 1
                if line['name'] == '110100 Stock Valuation':
                    new_line = dict()
                    new_line['name'] = 'Buffer Stock'
                    new_line['balance'] = value[0][0]
                    new_line['type'] = 'account'
                    new_line['level'] = 4
                    new_line['account_type'] = 'other'
                    new_line['debit'] = 0.0
                    new_line['credit'] = 0.0
                    report_lines.insert(cnt, new_line)

        return {
            'doc_ids': self.ids,
            'doc_model': self.model,
            'data': data['form'],
            'docs': docs,
            'time': time,
            'get_account_lines': report_lines
        }
