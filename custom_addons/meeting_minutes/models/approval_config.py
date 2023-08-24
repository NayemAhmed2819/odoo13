from odoo import api, fields, models


class ApprovalConfig(models.Model):
    _name = "approval.config"
    _description = "Approval Config"
    _rec_name = 'id'

    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    department = fields.Many2one('hr.department', string='Department', required=True)
    user_ids = fields.Many2many('hr.employee', string="Users", relation='approval_config_res_users_rel', required=True)
    approval_privilege = fields.Boolean('Active', default=True)

    @api.onchange('department')
    def _onchange_department(self):
        if self.department:
            employees = self.env['hr.employee'].search([('department_id', '=', self.department.id)])
            self.user_ids = employees
        else:
            self.user_ids = [(5,)]
