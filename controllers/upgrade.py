# -*- coding: utf-8 -*-

from general_helpers import max_string_length
from general_helpers import get_ajax_loader

from openstudio.os_workshop_product import WorkshopProduct
from openstudio.os_invoice import Invoice

from os_upgrade import set_version


def to_login(var=None):
    redirect(URL('default', 'user', args=['login']))


def index():
    """
        This function executes commands needed for upgrades to new versions
    """
    # first check if a version is set
    if not db.sys_properties(Property='Version'):
        db.sys_properties.insert(Property='Version',
                                 PropertyValue=0)
        db.sys_properties.insert(Property='VersionRelease',
                                 PropertyValue=0)

    # check if a version is set and get it
    if db.sys_properties(Property='Version'):
        version = float(db.sys_properties(Property='Version').PropertyValue)

        if version < 2019.14:
            print(version)
            upgrade_to_201914()
            session.flash = T("Upgraded db to 2019.14")
        if version < 2020.02:
            print(version)
            upgrade_to_202002()
            session.flash = T("Upgraded db to 2020.02")
        else:
            session.flash = T('Already up to date')

        # always renew permissions for admin group after update
        set_permissions_for_admin_group()

    set_version()

    ##
    # clear cache
    ##
    cache.ram.clear(regex='.*')

    # Back to square one
    to_login()


def upgrade_to_201914():
    """
        Upgrade operations to 2019.14
    """
    ## Set length for all barcode_id fields in auth_user to 14 (when they have a value)
    query = (db.auth_user.barcode_id != None) & \
            (db.auth_user.barcode_id != "")

    rows = db(query).select(db.auth_user.ALL)
    for row in rows:
        if len(row.barcode_id) > 13:
            row.barcode_id = row.barcode_id[1:]
        row.barcode = None
        row.update_record()


def upgrade_to_202002():
    """
        Upgrade operations to 2020.02
    """
    db.sys_email_templates.update_or_insert(
        (db.sys_email_templates.Name == 'subscription_created'),
        Name = 'subscription_created',
        Title = T("Subscription created"),
        TemplateContent = """<h3>Your subscription has been activated!</h3>
<p>&nbsp;</p>
<p>To view the active subscriptions in your profile, please click&nbsp;<a href="{link_profile_subscriptions}">here</a>.</p>"""
    )

    db.sys_email_templates.update_or_insert(
        (db.sys_email_templates.Name == 'trial_follow_up'),
        Name = 'trial_follow_up',
        Title = T("Trial follow up"),
        TemplateContent = """Dear {customer_name},

-- Please replace this text with your own to follow up on trial products. --"""
    )

