# -*- coding: utf-8 -*-
from datetime import date
from odoo import api, fields, models


class MeetingRoom(models.Model):
    _name = "meeting.room"
    _inherit = "mail.thread", "mail.activity.mixin"
    _description = "Meeting Room"
    _rec_name = 'room_name'

    room_name = fields.Char(string='Room Name', tracking=True, required=True)
    room_location = fields.Char(string='Location', tracking=True, required=True)
    capacity = fields.Integer(string='Capacity', required=True)
    description = fields.Text(string="Room Description")
    meeting_ids = fields.One2many('meeting.request', 'venue', string='Meetings')
    booking_count = fields.Integer(string='Booking(s)', compute='_compute_booking_count')

    @api.depends('meeting_ids')
    def _compute_booking_count(self):
        for room in self:
            room.booking_count = len(room.meeting_ids)