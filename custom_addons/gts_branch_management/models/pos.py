from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def create(self, vals):
        res = super(PosOrder, self).create(vals)
        res.branch_id = res.session_id.branch_id.id
        return res

    branch_id = fields.Many2one('res.branch', 'Branch')


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def create(self, vals):
        res = super(PosSession, self).create(vals)
        res.branch_id = res.config_id.branch_id.id
        return res

    branch_id = fields.Many2one('res.branch', 'Branch')


class PosConfig(models.Model):
    _inherit = 'pos.config'

    branch_id = fields.Many2one('res.branch', 'Branch')

    @api.multi
    @api.constrains('branch_id','stock_location_id')
    def _check_branch_constrains(self):
        if self.branch_id and self.stock_location_id:
            if self.branch_id.id != self.stock_location_id.branch_id.id:
                raise UserError(_(
                    'Configuration error\n You must select same branch on a location \
                    as assigned on a point of sale configuration.'
                ))
