from odoo import api, fields, models


class AppointmentReportWizard(models.TransientModel):
    _name = "meetings.report.wizard"
    _description = "Print Meetings Wizard"

    venue = fields.Many2one('meeting.room', string="Venue")
    date_from = fields.Datetime(string="Date From")
    date_to = fields.Datetime(string="Date To")

    def action_print_report(self):
        domain = []

        venue = self.venue
        if venue:
            domain += [('venue', '=', venue.id)]
        date_from = self.date_from
        if date_from:
            domain += [('start_datetime', '>=', date_from)]
        date_to = self.date_to
        if date_to:
            domain += [('start_datetime', '<=', date_to)]


        meetings = self.env['meeting.request'].search_read(domain)

        data = {
            'form': self.read()[0],
            'meetings': meetings,
        }
        print(meetings)
        return self.env.ref('meeting_minutes.action_report_meetings_new').report_action(self, data=data)
