# -*- coding: utf-8 -*-

"""
The OsScheduler class will hold all tasks that should run in the background (for now)
When it gets bit, let's split it into multiple files.

Naming:

Roughly stick to:
db_table.action.info_about_what_task_does

"""

import datetime
from gluon import *

class OsSchedulerTasks:

    def customers_subscriptions_create_invoices_for_month(self, year, month, description, invoice_date='today'):
        """
            Actually create invoices for subscriptions for a given month
        """
        from .os_customer_subscription import CustomerSubscription
        from general_helpers import get_last_day_month
        from .os_invoice import Invoice

        T = current.T
        db = current.db
        DATE_FORMAT = current.DATE_FORMAT


        year = int(year)
        month = int(month)

        firstdaythismonth = datetime.date(year, month, 1)
        lastdaythismonth  = get_last_day_month(firstdaythismonth)

        invoices_count = 0

        # get all active subscriptions in month
        query = (db.customers_subscriptions.Startdate <= lastdaythismonth) & \
                ((db.customers_subscriptions.Enddate >= firstdaythismonth) |
                 (db.customers_subscriptions.Enddate == None))

        rows = db(query).select(db.customers_subscriptions.ALL)
        for row in rows:
            cs = CustomerSubscription(row.id)
            cs.create_invoice_for_month(year, month, description, invoice_date)

            invoices_count += 1

        ##
        # For scheduled tasks db connection has to be committed manually
        ##
        db.commit()

        return T("Invoices in month") + ': ' + str(invoices_count)

        # csap = db.customers_subscriptions_alt_prices
        #
        # fields = [
        #     db.customers_subscriptions.id,
        #     db.customers_subscriptions.auth_customer_id,
        #     db.customers_subscriptions.school_subscriptions_id,
        #     db.customers_subscriptions.Startdate,
        #     db.customers_subscriptions.Enddate,
        #     db.customers_subscriptions.payment_methods_id,
        #     db.school_subscriptions.Name,
        #     db.school_subscriptions_price.Price,
        #     db.school_subscriptions_price.tax_rates_id,
        #     db.tax_rates.Percentage,
        #     db.customers_subscriptions_paused.id,
        #     db.invoices_items.id,
        #     csap.id,
        #     csap.Amount,
        #     csap.Description
        # ]
        #
        # rows = db.executesql(
        #     """
        #         SELECT cs.id,
        #                cs.auth_customer_id,
        #                cs.school_subscriptions_id,
        #                cs.Startdate,
        #                cs.Enddate,
        #                cs.payment_methods_id,
        #                ssu.Name,
        #                ssp.Price,
        #                ssp.tax_rates_id,
        #                tr.Percentage,
        #                csp.id,
        #                ii.invoices_items_id,
        #                csap.id,
        #                csap.Amount,
        #                csap.Description
        #         FROM customers_subscriptions cs
        #         LEFT JOIN auth_user au
        #          ON au.id = cs.auth_customer_id
        #         LEFT JOIN school_subscriptions ssu
        #          ON cs.school_subscriptions_id = ssu.id
        #         LEFT JOIN
        #          (SELECT id,
        #                  school_subscriptions_id,
        #                  Startdate,
        #                  Enddate,
        #                  Price,
        #                  tax_rates_id
        #           FROM school_subscriptions_price
        #           WHERE Startdate <= '{firstdaythismonth}' AND
        #                 (Enddate >= '{firstdaythismonth}' OR Enddate IS NULL)) ssp
        #          ON ssp.school_subscriptions_id = ssu.id
        #         LEFT JOIN tax_rates tr
        #          ON ssp.tax_rates_id = tr.id
        #         LEFT JOIN
        #          (SELECT id,
        #                  customers_subscriptions_id
        #           FROM customers_subscriptions_paused
        #           WHERE Startdate <= '{firstdaythismonth}' AND
        #                 (Enddate >= '{firstdaythismonth}' OR Enddate IS NULL)) csp
        #          ON cs.id = csp.customers_subscriptions_id
        #         LEFT JOIN
        #          (SELECT iics.id,
        #                  iics.invoices_items_id,
        #                  iics.customers_subscriptions_id
        #           FROM invoices_items_customers_subscriptions iics
        #           LEFT JOIN invoices_items ON iics.invoices_items_id = invoices_items.id
        #           LEFT JOIN invoices ON invoices_items.invoices_id = invoices.id
        #           WHERE invoices.SubscriptionYear = {year} AND invoices.SubscriptionMonth = {month}) ii
        #          ON ii.customers_subscriptions_id = cs.id
        #         LEFT JOIN
        #          (SELECT id,
        #                  customers_subscriptions_id,
        #                  Amount,
        #                  Description
        #           FROM customers_subscriptions_alt_prices
        #           WHERE SubscriptionYear = {year} AND SubscriptionMonth = {month}) csap
        #          ON csap.customers_subscriptions_id = cs.id
        #         WHERE cs.Startdate <= '{lastdaythismonth}' AND
        #               (cs.Enddate >= '{firstdaythismonth}' OR cs.Enddate IS NULL) AND
        #               ssp.Price <> 0 AND
        #               ssp.Price IS NOT NULL AND
        #               au.trashed = 'F'
        #     """.format(firstdaythismonth=firstdaythismonth,
        #                lastdaythismonth =lastdaythismonth,
        #                year=year,
        #                month=month),
        #   fields=fields)
        #
        # igpt = db.invoices_groups_product_types(ProductType = 'subscription')
        # igID = igpt.invoices_groups_id
        #
        # invoices_created = 0
        #
        # # Alright, time to create some invoices
        # for row in rows:
        #     if row.invoices_items.id:
        #         # an invoice already exists, do nothing
        #         continue
        #     if row.customers_subscriptions_paused.id:
        #         # the subscription is paused, don't create an invoice
        #         continue
        #     if row.customers_subscriptions_alt_prices.Amount == 0:
        #         # Don't create an invoice if there's an alt price for the subscription with amount 0.
        #         continue
        #
        #     csID = row.customers_subscriptions.id
        #     cuID = row.customers_subscriptions.auth_customer_id
        #     pmID = row.customers_subscriptions.payment_methods_id
        #
        #     subscr_name = row.school_subscriptions.Name
        #
        #     if row.customers_subscriptions_alt_prices.Description:
        #         inv_description = row.customers_subscriptions_alt_prices.Description
        #     else:
        #         inv_description = description
        #
        #     if row.customers_subscriptions.Startdate > firstdaythismonth:
        #         period_begin = row.customers_subscriptions.Startdate
        #     else:
        #         period_begin = firstdaythismonth
        #
        #     period_end = lastdaythismonth
        #     if row.customers_subscriptions.Enddate:
        #         if row.customers_subscriptions.Enddate >= firstdaythismonth and \
        #            row.customers_subscriptions.Enddate < lastdaythismonth:
        #             period_end = row.customers_subscriptions.Enddate
        #
        #
        #     item_description = period_begin.strftime(DATE_FORMAT) + ' - ' + \
        #                        period_end.strftime(DATE_FORMAT)
        #
        #     iID = db.invoices.insert(
        #         invoices_groups_id = igID,
        #         payment_methods_id = pmID,
        #         SubscriptionYear = year,
        #         SubscriptionMonth = month,
        #         Description = inv_description,
        #         Status = 'sent'
        #     )
        #
        #     # create object to set Invoice# and due date
        #     invoice = Invoice(iID)
        #     invoice.link_to_customer(cuID)
        #     iiID = invoice.item_add_subscription(csID, year, month)
        #     invoice.link_item_to_customer_subscription(csID, iiID)
        #     invoice.set_amounts()
        #
        #     invoices_created += 1

        # ##
        # # For scheduled tasks db connection has to be committed manually
        # ##
        # db.commit()
        #
        # return T("Invoices created") + ': ' + unicode(invoices_created)


    def customers_subscriptions_add_credits_for_month(self, year, month):
        """
        :param year: int
        :param month: int
        :return: Add customer subscription credits for month
        """
        from .os_customers_subscriptions_credits import CustomersSubscriptionsCredits

        T = current.T
        db = current.db

        year = int(year)
        month = int(month)

        csch = CustomersSubscriptionsCredits()
        added = csch.add_credits(year, month)

        db.commit()

        return T("Subscriptions for which credits were added") + ': ' + str(added)


    def customers_memberships_renew_expired(self, year, month):
        """
            Checks if a subscription exceeds the expiration of a membership.
            If so it creates a new membership and an invoice for it for the customer
        """
        from general_helpers import get_last_day_month
        from datetime import timedelta
        from .os_customer import Customer
        from .os_invoice import Invoice
        from .os_school_membership import SchoolMembership

        T = current.T
        db = current.db
        DATE_FORMAT = current.DATE_FORMAT

        year = int(year)
        month = int(month)

        firstdaythismonth = datetime.date(year, month, 1)
        lastdaythismonth  = get_last_day_month(firstdaythismonth)
        firstdaynextmonth = lastdaythismonth + datetime.timedelta(days=1)

        query = (db.customers_memberships.Enddate >= firstdaythismonth) & \
                (db.customers_memberships.Enddate <= lastdaythismonth)

        rows = db(query).select(
            db.customers_memberships.ALL
        )

        renewed = 0

        for row in rows:
            new_cm_start = row.Enddate + datetime.timedelta(days=1)

            # Check if a subscription will be active next month for customer
            # if so, add another membership
            customer = Customer(row.auth_customer_id)

            # Check if a new membership hasn't ben added already
            if customer.has_membership_on_date(new_cm_start):
                continue

            day_after_current_membership_end = row.Enddate + datetime.timedelta(days=1)
            # Ok all good, continue
            if customer.has_subscription_on_date(day_after_current_membership_end, from_cache=False):
                new_cm_start = row.Enddate + datetime.timedelta(days=1)

                school_membership = SchoolMembership(row.school_memberships_id)

                school_membership.sell_to_customer(
                    row.auth_customer_id,
                    new_cm_start,
                    note=T("Renewal for membership %s" % row.id),
                    invoice=True,
                    payment_methods_id=row.payment_methods_id
                )

                renewed += 1
            # else:
            #
            #     print 'no subscription'
            # print renewed

        ##
        # For scheduled tasks db connection has to be committed manually
        ##
        db.commit()

        return T("Memberships renewed") + ': ' + str(renewed)


    def email_teachers_sub_requests_daily_summary(self):
        """
        Send a daily summary of open sub requests to each teacher for the classtypes
        they're allowed to teach
        :return:
        """
        from .os_mail import OsMail
        from .os_teachers import Teachers

        db = current.db
        T = current.T
        os_mail = OsMail()

        # Get list of teachers
        teachers = Teachers()
        teacher_id_rows = teachers.get_teacher_ids()

        mails_sent = 0
        for row in teacher_id_rows:
            os_mail = OsMail()
            result = os_mail.render_email_template(
                'teacher_sub_requests_daily_summary',
                auth_user_id=row.id,
                return_html=True
            )

            send_result = False
            if not result['error']:
                send_result = os_mail.send(
                    message_html=result['html_message'],
                    message_subject=T("Daily summary - open classes"),
                    auth_user_id=row.id
                )

            if send_result:
                mails_sent += 1

        return "Sent mails: %s" % mails_sent


    def email_reminders_teachers_sub_request_open(self):
        """
        Send teachers reminders when a sub for their class hasn't been found yet.
        :return:
        """
        from openstudio.os_class import Class
        from openstudio.os_mail import OsMail
        from openstudio.os_sys_email_reminders import SysEmailReminders

        T = current.T
        db = current.db
        TODAY_LOCAL = current.TODAY_LOCAL

        # Check if reminders configured
        sys_reminders = SysEmailReminders('teachers_sub_request_open')
        reminders = sys_reminders.list()

        mails_sent = 0
        for reminder in reminders:
            # Get list of open classes on reminder date
            reminder_date = TODAY_LOCAL + datetime.timedelta(reminder.Days)

            query = (db.classes_otc.Status == 'open') & \
                    (db.classes_otc.ClassDate == reminder_date)

            rows = db(query).select(db.classes_otc.ALL)
            for row in rows:
                clsID = row.classes_id
                cls = Class(clsID, row.ClassDate)
                regular_teachers = cls.get_regular_teacher_ids()

                if not regular_teachers['error']:
                    auth_teacher_id = regular_teachers['auth_teacher_id']
                    teacher = db.auth_user(auth_teacher_id)

                    os_mail = OsMail()
                    result = os_mail.render_email_template(
                        'teacher_sub_request_open_reminder',
                        classes_otc_id=row.id,
                        return_html=True
                    )

                    send_result = False
                    if not result['error']:
                        send_result = os_mail.send(
                            message_html=result['html_message'],
                            message_subject=T("Reminder - open class"),
                            auth_user_id=auth_teacher_id
                        )

                    if send_result:
                        mails_sent += 1

            # send reminder to teacher

        return "Sent mails: %s" % mails_sent


    def email_trailclass_follow_up(self):
        """
        Send teachers reminders when a sub for their class hasn't been found yet.
        :return:
        """
        from openstudio.os_mail import OsMail

        T = current.T
        db = current.db
        os_mail = OsMail()
        TODAY_LOCAL = current.TODAY_LOCAL
        yesterday = TODAY_LOCAL - datetime.timedelta(days=1)

        left = [
            db.auth_user.on(
                db.classes_attendance.auth_customer_id ==
                db.auth_user.id
            )
        ]

        query = (db.classes_attendance.ClassDate == yesterday) & \
                (db.classes_attendance.AttendanceType == 1) # Trial

        rows = db(query).select(db.classes_attendance.ALL,
                                db.auth_user.display_name,
                                left=left)

        mails_sent = 0

        for row in rows:
            result = os_mail.render_email_template(
                'trial_follow_up',
                classes_attendance_id = row.classes_attendance.id,
                return_html = True
            )

            os_mail.send(
                message_html = result['html_message'],
                message_subject = result['msg_subject'],
                auth_user_id = row.classes_attendance.auth_customer_id
            )

            mails_sent += 1

        return "Sent trial class follow up mails: %s" % mails_sent


    def email_trailcard_follow_up(self):
        """
        Send teachers reminders when a sub for their class hasn't been found yet.
        :return:
        """
        from openstudio.os_mail import OsMail

        T = current.T
        db = current.db
        os_mail = OsMail()
        TODAY_LOCAL = current.TODAY_LOCAL
        yesterday = TODAY_LOCAL - datetime.timedelta(days=1)

        left = [
            db.school_classcards.on(
                db.customers_classcards.school_classcards_id ==
                db.school_classcards.id
            ),
            db.auth_user.on(
                db.customers_classcards.auth_customer_id ==
                db.auth_user.id
            )
        ]

        query = (db.school_classcards.Trialcard == True) & \
                (db.customers_classcards.Enddate == yesterday)

        rows = db(query).select(db.customers_classcards.ALL,
                                db.auth_user.display_name,
                                left=left)

        mails_sent = 0

        for row in rows:
            result = os_mail.render_email_template(
                'trial_follow_up',
                customers_classcards_id = row.customers_classcards.id,
                return_html = True
            )

            os_mail.send(
                message_html = result['html_message'],
                message_subject = result['msg_subject'],
                auth_user_id = row.customers_classcards.auth_customer_id
            )

            mails_sent += 1

        return "Sent trial card follow up mails: %s" % mails_sent

