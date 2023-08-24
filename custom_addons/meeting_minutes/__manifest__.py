# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


{
    'name': 'Meeting Minutes',
    'version': '1.1.0',
    'category': 'Meeting',
    'author': 'Md. Nayem Ahmed',
    'sequence': -100,
    'summary': 'Meeting Management System',
    'description': """Meeting Management System""",
    'depends': ['mail', 'product', 'gts_branch_management', 'board'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'wizard/meetings_report_view.xml',
        'views/menu.xml',
        'views/room_view.xml',
        'views/approval_config_view.xml',
        'views/meeting_view.xml',
        'views/dashboard.xml',
        'report/report_meeting_details.xml',
        'report/meetings_report_wizard.xml',
        'report/report.xml',
    ],
    'demo': [],
    'application': True,
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
