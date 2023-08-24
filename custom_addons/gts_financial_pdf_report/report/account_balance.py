# -*- coding: utf-8 -*-

import time
from odoo import api, models, _
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DATE_FORMAT
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DATETIME_FORMAT, datetime, relativedelta
from datetime import date


class ReportTrialBalance(models.AbstractModel):
    _name = 'report.gts_financial_pdf_report.report_trialbalance'

    def _get_accounts(self, accounts,initial_balance, display_account, from_date, company_id, to_date,target_move):
        print(company_id)
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
            start_date = datetime.strptime(from_date, DATE_FORMAT)
            account_result_ini = {}  # for initial balance
            # Initial Balance for trial Balance (add by raihan)
            # request_ini = (
            #         "SELECT account_id AS id,0 as initial_balance, SUM(debit) AS debit, SUM(credit) AS credit, (SUM(debit) - SUM(credit)) AS balance" + \
            #         " FROM " + tables + " WHERE account_move_line.parent_state != 'cancel' and account_move_line.company_id= %s AND account_id IN %s "
            #                             "and account_move_line.date::DATE < '{}'::DATE " + filters + " GROUP BY account_id")
            # params = (company_id[0], tuple(accounts.ids), start_date.strftime(DATETIME_FORMAT), ) + tuple(where_params)

            # request_ini = """SELECT account_id AS id,COALESCE((SUM(debit) - SUM(credit)),0) AS initial_balance
            #                  FROM """ + tables +""" WHERE  account_move_line.company_id= %s AND account_id IN %s and account_move_line.date < %s AND ("account_move_line"."move_id"="account_move_line__move_id"."id")
            #                  AND ("account_move_line__move_id"."state" in ('draft', 'posted')) """+filters+"""GROUP BY account_id"""
            #
            # params = (company_id[0], tuple(accounts.ids), start_date.strftime(DATETIME_FORMAT),) + tuple(where_params)

            #****************************************BT************************************************
            # request_ini = (
            #         "SELECT account_id AS id,(SUM(debit) - SUM(credit)) AS initial_balance" + \
            #         " FROM account_move left join account_move_line on account_move.id=account_move_line.move_id WHERE account_move_line.parent_state in ('draft', 'posted') and account_move_line.company_id= %s AND account_id IN %s "
            #         "and account_move_line.date::DATE < %s::DATE GROUP BY account_id")
            # params = (company_id[0], tuple(accounts.ids), start_date.strftime(DATETIME_FORMAT),)
            # ****************************************BT************************************************
            where_state = ['posted']
            if target_move == 'all':
                where_state.append('draft')
            if initial_balance:
                request_ini = (
                        "SELECT account_id AS id,(SUM(debit) - SUM(credit)) AS initial_balance" + \
                        " FROM account_move left join account_move_line on account_move.id=account_move_line.move_id WHERE account_move_line.company_id= %s AND account_id IN %s "
                        "and account_move_line.date::DATE < %s::DATE and account_move.state in %s  GROUP BY account_id ")
                params = (company_id[0], tuple(accounts.ids), start_date.strftime(DATETIME_FORMAT),tuple(where_state))
            else:
                request_ini = (
                "SELECT account_id AS id,0 AS initial_balance" + \
                " FROM account_move left join account_move_line on account_move.id=account_move_line.move_id WHERE account_move_line.company_id= %s AND account_id IN %s "
                "and account_move_line.date::DATE < %s::DATE and account_move.state in %s  GROUP BY account_id ")
                params = (company_id[0], tuple(accounts.ids), start_date.strftime(DATETIME_FORMAT), tuple(where_state))

            self.env.cr.execute(request_ini, params)
            for init_row in self.env.cr.dictfetchall():
                account_result_ini[init_row.pop('id')] = init_row

            # for m in account_result:
            #     for d in account_result_ini:
            #         if m == d:
            #             account_result[m]['initial_balance'] = account_result_ini[d].get('initial_balance')
            #             break

            for m in account_result_ini:
                if m in account_result:
                    account_result[m]['initial_balance'] = account_result_ini[m].get('initial_balance')
                else:
                    account_result[m] = dict()
                    account_result[m]['initial_balance'] = account_result_ini[m]['initial_balance']
                    account_result[m]['debit'] = 0.0
                    account_result[m]['credit'] = 0.0
                    account_result[m]['balance'] = 0.0


                    # if m == d:
                    #     account_result[m]['initial_balance'] = account_result_ini[d].get('initial_balance')
                    #     break
                    # else:
                    #     account_result[m]['initial_balance'] = account_result_ini[d].get('initial_balance')

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
            #         from_date_condition = "aml.date::DATE >='" + from_date + "'::DATE"
            #     if to_date:
            #         to_date_condition = "aml.date::DATE <='" + to_date + "'::DATE"
            #     # if from_date and to_date:
            #     query = """select COALESCE(SUM(debit),0) - COALESCE(SUM(credit), 0) as balance, COALESCE(SUM(debit), 0) as debit, COALESCE(SUM(credit), 0) as credit from account_move_line aml
            #                 inner join account_move am on am.id = aml.move_id where account_id = {} and aml.company_id = {} and am.state in ('draft', 'posted') and {} and {}
            #             """.format(account.id, company_id[0], from_date_condition, to_date_condition)
            #     if from_date:
            #         query_ini = """select COALESCE((SUM(debit) - SUM(credit)),0) AS initial_balance from account_move_line aml inner join account_move as am on am.id = aml.move_id where aml.account_id = {}
            #                 and aml.company_id = {} and am.state in ('draft', 'posted') and aml.date::DATE < '{}'::DATE """.format(account.id, company_id[0], from_date)
            #         self._cr.execute(query_ini)
            #         init_value = self.env.cr.dictfetchall()
            #     else:
            #         init_value = 0
            #
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
            # if display_account == 'not_zero' and not currency.is_zero(res['balance']):
            #     account_res.append(res)
            if display_account == 'movement' and (
                    not currency.is_zero(res['debit']) or not currency.is_zero(res['credit']) or not currency.is_zero(res['initial_balance'])):
                account_res.append(res)
        return account_res

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form') or not self.env.context.get('active_model'):
            raise UserError(_("Form content is missing, this report cannot be printed."))

        self.model = self.env.context.get('active_model')
        docs = self.env[self.model].browse(self.env.context.get('active_ids', []))
        display_account = data['form'].get('display_account')
        accounts = docs if self.model == 'account.account' else self.env['account.account'].search([])
        company_id = data['form']['company_id']
        from_date = data['form']['date_from']
        to_date = data['form']['date_to']
        target_move=data['form']['target_move']
        init_balance = data['form'].get('initial_balance', True)
        account_res = self.with_context(data['form'].get('used_context'))._get_accounts(accounts,init_balance, display_account,
                                                                                        from_date, company_id, to_date,target_move)
        print('account res', account_res)
        return {
            'doc_ids': self.ids,
            'doc_model': self.model,
            'data': data['form'],
            'docs': docs,
            'time': time,
            'Accounts': account_res,
        }
