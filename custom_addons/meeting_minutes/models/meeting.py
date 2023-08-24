# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MeetingRequest(models.Model):
    _name = 'meeting.request'
    _inherit = "mail.thread", "mail.activity.mixin"
    _description = 'Meeting Request'
    _rec_name = 'ref'

    title = fields.Char(string='Title', required=True)
    ref = fields.Char(string='Reference', tracking=True)
    description = fields.Text(string='Description')
    start_datetime = fields.Datetime(string='Start Date & Time', required=True)
    end_datetime = fields.Datetime(string='End Date & Time', required=True)
    total_hours = fields.Float(string='Total Hours', compute='_compute_total_hours', store=True)
    coordinator = fields.Many2one('res.partner', string='Coordinator', required=True)
    participants = fields.Many2many('res.partner', string='Participants', required=True)
    venue = fields.Many2one('meeting.room', string='Venue', required=True)
    state = fields.Selection([
        ('drafted', 'Drafted'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved & Booked'),
        ('done', 'Meeting Minutes Done'),
        ('rejected', 'Rejected'),
    ], string='Status', default='drafted')
    show_button = fields.Boolean(string="Show Button", compute="_compute_show_button", default=False)
    loc = fields.Char(string="Location", readonly=True)
    cap = fields.Char(string="Capacity", readonly=True)
    desc = fields.Char(string="Description", readonly=True)
    is_converted_to_minutes = fields.Boolean(string="Conversion", default=False)
    prepared_by = fields.Char(string="Prepared By", compute='_compute_prepared_by_name', store=True, readonly=True)
    discussion = fields.Html(string='Discussion & Decision')
    decision = fields.Html(string='Agreed Decision for Next Step')

    @api.onchange('venue')
    def _onchange_venue(self):
        if self.venue:
            self.loc = self.venue.room_location
            self.cap = self.venue.capacity
            self.desc = self.venue.description

    # @api.constrains('participants', 'venue')
    # def _check_room_capacity(self):
    #     for meeting in self:
    #         if meeting.venue and meeting.participants:
    #             if len(meeting.participants) > meeting.venue.capacity:
    #                 raise ValidationError("Participants exceed room capacity")

    @api.constrains('start_datetime', 'end_datetime', 'venue')
    def _check_overlapping_meetings(self):
        for request in self:
            if request.venue and request.start_datetime and request.end_datetime:
                overlapping_meetings = self.env['meeting.request'].search([
                    ('id', '!=', request.id),
                    ('venue', '=', request.venue.id),
                    ('start_datetime', '<', request.end_datetime),
                    ('end_datetime', '>', request.start_datetime),
                ])

                overlapping_meetings_same_date = overlapping_meetings.filtered(
                    lambda meeting: (
                            meeting.start_datetime.date() == request.start_datetime.date() or
                            meeting.end_datetime.date() == request.start_datetime.date() or
                            meeting.start_datetime.date() == request.end_datetime.date() or
                            meeting.end_datetime.date() == request.end_datetime.date()
                    )
                )

                if overlapping_meetings_same_date:
                    raise ValidationError("The room is already booked for the selected time.")

    @api.depends('start_datetime', 'end_datetime')
    def _compute_total_hours(self):
        for rec in self:
            if rec.start_datetime and rec.end_datetime:
                # Calculate the difference in hours between start and end date times
                delta = rec.end_datetime - rec.start_datetime
                total_hours = delta.total_seconds() / 3600.0  # Convert seconds to hours
                rec.total_hours = total_hours
            else:
                rec.total_hours = 0.0


    def action_submit(self):
        for rec in self:
            if rec.state == 'drafted':
                rec.state = 'pending_approval'

    @api.depends('title')
    def _compute_prepared_by_name(self):
        for request in self:
            # Get the currently logged-in user's display name from the context
            user_name = self.env.context.get('user_name', self.env.user.display_name)
            # Set the value of the prepared_by field
            request.prepared_by =user_name

    @api.depends_context('user_id')
    def _compute_show_button(self):
        query = """SELECT hr_employee_id FROM approval_config_res_users_rel"""
        self._cr.execute(query=query)
        result = self._cr.fetchall()

        current_user = self.env.user
        employee = self.env['hr.employee'].search([('user_id', '=', current_user.id)], limit=1)

        approval = self.env['approval.config'].search([]).approval_privilege

        for rec in result:
            if employee.id == rec[0] and approval == True:
                self.show_button = True
                break
            else:
                self.show_button = False

        # Could use the following single line code instead of the loop:
        # self.show_button = any(employee.id == rec[0] for rec in result)


    def action_submission_cancel(self):
        for rec in self:
            if rec.state == 'pending_approval':
                rec.state = 'drafted'

    def action_approve(self):
        for rec in self:
            if rec.state == 'pending_approval':
                rec.state = 'approved'
                # rec.create_meeting_minutes()

    def action_rejected(self):
        for rec in self:
            if rec.state == 'pending_approval':
                rec.state = 'rejected'

    def action_done(self):
        for rec in self:
            if rec.state == 'approved':
                if rec.discussion == '<p><br></p>' and rec.decision == '<p><br></p>':
                    raise ValidationError("Discussion and Decision fields must be filled before marking the meeting as done.")
                rec.state = 'done'

    # def create_meeting_minutes(self):
    #     for rec in self:
    #         if rec.state == 'approved':
    #             participant_ids = [(6, 0, rec.participants.ids)]  # Convert IDs to list of tuples
    #             minutes_vals = {
    #                 'meeting_request_id': rec.id,
    #                 'title': rec.title,
    #                 'ref': rec.ref,
    #                 'description': rec.description,
    #                 'start_datetime': rec.start_datetime,
    #                 'end_datetime': rec.end_datetime,
    #                 'total_hours': rec.total_hours,
    #                 'prepared_by': rec.prepared_by,
    #                 'coordinator': rec.coordinator.id,
    #                 'participants': participant_ids,
    #                 'venue': rec.venue.id,
    #                 'loc': rec.loc,
    #                 'cap': rec.cap,
    #                 'desc': rec.desc,
    #                 # Copy other relevant fields from 'meeting.request'
    #             }
    #             self.env['meeting.minutes'].create(minutes_vals)
    #
    #             # Mark meeting.request as converted
    #             rec.write({'is_converted_to_minutes': True})

    @api.model
    def create(self, vals):
        vals['ref'] = self.env['ir.sequence'].next_by_code('meeting.request')
        return super(MeetingRequest, self).create(vals)

    def write(self, vals):
        # Allow the write operation if it's triggered by specific fields or actions

        bypass_check = self.env.context.get('bypass_check', False)
        if not bypass_check and any(rec.state in ['pending_approval'] for rec in self):
            raise ValidationError("You cannot edit while the status is pending for approval.")

        bypass_check = self.env.context.get('bypass_check', False)
        if not bypass_check and any(rec.state in ['done'] for rec in self):
            raise ValidationError("You cannot edit a done meeting minutes.")

        bypass_check = self.env.context.get('bypass_check', False)
        if not bypass_check and any(rec.state in ['rejected'] for rec in self):
            raise ValidationError("You cannot edit a rejected booking.")

        # Update the 'ref' field if needed
        if not self.ref and not vals.get('ref'):
            vals['ref'] = self.env['ir.sequence'].next_by_code('meeting.request')

        return super(MeetingRequest, self).write(vals)
