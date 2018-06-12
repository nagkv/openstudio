# -*- coding: utf-8 -*-
import datetime
import calendar
import random
import os

from decimal import Decimal, ROUND_HALF_UP

from gluon import *
from general_helpers import get_last_day_month
from general_helpers import workshops_get_full_workshop_product_id
from general_helpers import max_string_length
from general_helpers import NRtoDay
from general_helpers import represent_validity_units


from openstudio.os_customer import Customer





class CustomerSubscription:
    '''
        Class that contains functions for customer subscriptions
    '''
    def __init__(self, csID):
        '''
            Class init function which sets csID
        '''
        db = current.db

        self.csID = csID
        self.cs = db.customers_subscriptions(csID)

        self.ssuID = self.cs.school_subscriptions_id
        self.ssu   = db.school_subscriptions(self.ssuID)

        self.name               = self.ssu.Name
        self.auth_customer_id   = self.cs.auth_customer_id
        self.payment_methods_id = self.cs.payment_methods_id
        self.startdate          = self.cs.Startdate
        self.enddate            = self.cs.Enddate


    def create_invoice_for_month(self, SubscriptionYear, SubscriptionMonth):
        """
            :param SubscriptionYear: Year of subscription
            :param SubscriptionMonth: Month of subscription
        """
        db = current.db
        TODAY_LOCAL = current.TODAY_LOCAL
        DATE_FORMAT = current.DATE_FORMAT

        # create invoice linked to subscription for first subscription term to know the right amount.
        SubscriptionYear = TODAY_LOCAL.year
        SubscriptionMonth = TODAY_LOCAL.month

        firstdaythismonth = datetime.date(SubscriptionYear, SubscriptionMonth, 1)
        lastdaythismonth = get_last_day_month(firstdaythismonth)

        left = [ db.invoices_customers_subscriptions.on(
            db.invoices_customers_subscriptions.invoices_id ==
            db.invoices.id
        )]

        # Check if an invoice already exists, if so, return invoice id
        query = (db.invoices_customers_subscriptions.customers_subscriptions_id == self.csID) & \
                (db.invoices.SubscriptionYear == SubscriptionYear) & \
                (db.invoices.SubscriptionMonth == SubscriptionMonth)
        rows = db(query).select(db.invoices.ALL,
                                left=left)
        if len(rows):
            return rows.first().id

        # Check if the subscription is paused
        query = (db.customers_subscriptions_paused.customers_subscriptions_id == self.csID) & \
                (db.customers_subscriptions_paused.Startdate <= lastdaythismonth) & \
                ((db.customers_subscriptions_paused.Enddate >= firstdaythismonth) |
                 (db.customers_subscriptions_paused.Enddate == None))
        if db(query).count():
            return

        # Check if an alt. price with amount 0 has been defined
        csap = db.customers_subscriptions_alt_prices
        query = (csap.customers_subscriptions_id == self.csID) & \
                (csap.SubscriptionYear == SubscriptionYear) & \
                (csap.SubscriptionMonth == SubscriptionMonth)
        csap_rows = db(query).select(csap.ALL)
        if csap_rows:
            csap_row = csap_rows.first()
            if csap_row.Amount == 0:
                return

        # Ok we've survived all checks, continue with invoice creation
        igpt = db.invoices_groups_product_types(ProductType='subscription')
        igID = igpt.invoices_groups_id

        if TODAY_LOCAL > firstdaythismonth:
            period_begin = TODAY_LOCAL
        else:
            period_begin = firstdaythismonth

        period_end = lastdaythismonth
        if self.enddate:
            if self.startdate >= firstdaythismonth and \
               self.enddate < lastdaythismonth:
                period_end = self.enddate

        item_description = period_begin.strftime(DATE_FORMAT) + ' - ' + \
                           period_end.strftime(DATE_FORMAT)

        iID = db.invoices.insert(
            invoices_groups_id=igID,
            payment_methods_id=self.payment_methods_id,
            customers_subscriptions_id=self.csID,
            SubscriptionYear=SubscriptionYear,
            SubscriptionMonth=SubscriptionMonth,
            Description='',
            Status='sent'
        )

        # create object to set Invoice# and due date
        invoice = Invoice(iID)
        invoice.link_to_customer(self.auth_customer_id)
        invoice.link_to_customer_subscription(self.csID)
        invoice.item_add_subscription(SubscriptionYear, SubscriptionMonth)

        return iID


    def get_credits_balance(self):
        '''
            Calculate total credits remaining for a subscription
        '''
        db = current.db

        sum = db.customers_subscriptions_credits.MutationAmount.sum()

        query = (db.customers_subscriptions_credits.MutationType == 'add') & \
                (db.customers_subscriptions_credits.customers_subscriptions_id == self.csID)
        add_total = db(query).select(sum).first()[sum] or 0

        query = (db.customers_subscriptions_credits.MutationType == 'sub') & \
                (db.customers_subscriptions_credits.customers_subscriptions_id == self.csID)
        sub_total = db(query).select(sum).first()[sum] or 0

        return round(add_total - sub_total, 1)


    def get_credits_mutations_rows(self,
                                   formatted=False,
                                   editable=False,
                                   deletable=False,
                                   delete_controller='',
                                   delete_function=''):
        '''
            Returns raw rows of credit mutations for a subscription
        '''
        os_gui = current.globalenv['os_gui']
        auth = current.auth
        db = current.db
        T = current.T

        left = [ db.classes_attendance.on(db.customers_subscriptions_credits.classes_attendance_id ==
                                          db.classes_attendance.id),
                 db.classes.on(db.classes_attendance.classes_id ==
                               db.classes.id) ]

        query = (db.customers_subscriptions_credits.customers_subscriptions_id == self.csID)
        rows = db(query).select(db.customers_subscriptions_credits.ALL,
                                db.classes.Starttime,
                                db.classes.Endtime,
                                db.classes.school_locations_id,
                                db.classes.school_classtypes_id,
                                db.classes_attendance.auth_customer_id,
                                db.classes_attendance.ClassDate,
                                left=left,
                                orderby=~db.customers_subscriptions_credits.MutationDateTime)

        if not formatted:
            return rows
        else:
            edit_permission = (auth.has_membership(group_id='Admins') or
                               auth.has_permission('update', 'customers_subscriptions_credits'))

            delete_permission = (auth.has_membership(group_id='Admins') or
                                 auth.has_permission('delete', 'customers_subscriptions_credits'))

            header = THEAD(TR(TH(T('Date')),
                              TH(T('Description')),
                              TH(T('Credits')),
                              TH(db.customers_subscriptions_credits.MutationType.label), # MutationType
                              TH(),
                              ))

            table = TABLE(header, _class='table table-striped table-hover')
            for i, row in enumerate(rows):
                repr_row = list(rows[i:i + 1].render())[0]

                csID = row.customers_subscriptions_credits.customers_subscriptions_id
                cuID = self.auth_customer_id

                delete = ''
                edit = ''
                if deletable and delete_permission:
                    confirm_msg = T("Really delete this mutation?")
                    onclick_del = "return confirm('" + confirm_msg + "');"

                    rvars = {'csID':csID,
                             'cuID':cuID,
                             'cscID':row.customers_subscriptions_credits.id}

                    delete = os_gui.get_button('delete_notext',
                                               URL(delete_controller, delete_function, vars=rvars),
                                               onclick=onclick_del,
                                               _class='pull-right')
                if editable and edit_permission:
                    edit = os_gui.get_button('edit',
                        URL('customers', 'subscription_credits_edit', vars=rvars))

                buttons = DIV(edit, delete, _class='pull-right')

                tr = TR(TD(repr_row.customers_subscriptions_credits.MutationDateTime),
                        TD(repr_row.customers_subscriptions_credits.Description),
                        TD(repr_row.customers_subscriptions_credits.MutationAmount),
                        TD(SPAN(repr_row.customers_subscriptions_credits.MutationType)),
                        TD(buttons))

                table.append(tr)

            return table


    def add_credits_month(self, year, month):
        '''
            Add credits for selected month
        '''
        first_day = datetime.date(year, month, 1)
        last_day = get_last_day_month(first_day)

        if self.cs.Startdate <= first_day:
            p_start = first_day
        else:
            p_start = self.cs.Startdate

        if self.cs.Enddate is None or self.cs.Enddate >= last_day:
            p_end = last_day
        else:
            p_end = self.cs.Enddate

        csch = CustomersSubscriptionsCredits()
        csch.add_subscription_credits_month(
            self.csID,
            self.cs.auth_customer_id,
            year,
            month,
            p_start,
            p_end,
            self.ssu.Classes,
            self.ssu.SubscriptionUnit,
            batch_add=False,
            book_classes=False)


    def _get_allowed_classes_format(self, class_ids):
        '''
            :param class_ids: list of db.classes.id
            :return: html table
        '''
        T = current.T
        db = current.db
        TODAY_LOCAL = current.TODAY_LOCAL

        query = (db.classes.AllowAPI == True) & \
                (db.classes.id.belongs(class_ids)) & \
                (db.classes.Startdate <= TODAY_LOCAL) & \
                ((db.classes.Enddate == None) |
                 (db.classes.Enddate >= TODAY_LOCAL))
        rows = db(query).select(db.classes.ALL,
                                orderby=db.classes.Week_day|db.classes.Starttime|db.classes.school_locations_id)

        header = THEAD(TR(TH(T('Day')),
                          TH(T('Time')),
                          TH(T('Location')),
                          TH(T('Class'))))
        table = TABLE(header, _class='table table-striped table-hover')
        for i, row in enumerate(rows):
            repr_row = list(rows[i:i + 1].render())[0]

            tr = TR(TD(repr_row.Week_day),
                    TD(repr_row.Starttime, ' - ', repr_row.Endtime),
                    TD(repr_row.school_locations_id),
                    TD(repr_row.school_classtypes_id))

            table.append(tr)

        return table


    def get_allowed_classes_enrollment(self, public_only=True, formatted=False):
        '''
            :return: return: list of db.classes.db that are allowed to be enrolled in using this subscription
        '''
        permissions = self.get_class_permissions(public_only=public_only)
        class_ids = []
        for clsID in permissions:
            try:
                if permissions[clsID]['Enroll']:
                    class_ids.append(clsID)
            except KeyError:
                pass

        if not formatted:
            return class_ids
        else:
            return self._get_allowed_classes_format(class_ids)


    def get_allowed_classes_booking(self, public_only=True, formatted=False):
        '''
            :return: return: list of db.classes.db that are allowed to be booked using this subscription
        '''
        permissions = self.get_class_permissions(public_only=public_only)
        class_ids = []
        for clsID in permissions:
            try:
                if permissions[clsID]['ShopBook']:
                    class_ids.append(clsID)
            except KeyError:
                pass


        if not formatted:
            return class_ids
        else:
            return self._get_allowed_classes_format(class_ids)


    def get_allowed_classes_attend(self, public_only=True, formatted=False):
        '''
            :return: return list of db.classes that are allowed to be attended using this subscription
        '''
        permissions = self.get_class_permissions(public_only=public_only)
        class_ids = []
        for clsID in permissions:
            try:
                if permissions[clsID]['Attend']:
                    class_ids.append(clsID)
            except KeyError:
                pass


        if not formatted:
            return class_ids
        else:
            return self._get_allowed_classes_format(class_ids)


    def _get_class_permissions_format(self, permissions):
        '''
            :param permissions: dictionary of class permissions
            :return: html table
        '''
        T = current.T
        db = current.db
        os_gui = current.globalenv['os_gui']
        TODAY_LOCAL = current.TODAY_LOCAL

        class_ids = []
        for clsID in permissions:
            class_ids.append(clsID)

        query = (db.classes.AllowAPI == True) & \
                (db.classes.id.belongs(class_ids)) & \
                (db.classes.Startdate <= TODAY_LOCAL) & \
                ((db.classes.Enddate == None) |
                 (db.classes.Enddate >= TODAY_LOCAL))
        rows = db(query).select(db.classes.ALL,
                                orderby=db.classes.Week_day|db.classes.Starttime|db.classes.school_locations_id)

        header = THEAD(TR(TH(T('Day')),
                          TH(T('Time')),
                          TH(T('Location')),
                          TH(T('Class')),
                          TH(T('Enroll')),
                          TH(T('Book in advance')),
                          TH(T('Attend'))))

        table = TABLE(header, _class='table table-striped table-hover')
        green_check = SPAN(os_gui.get_fa_icon('fa-check'), _class='text-green')

        for i, row in enumerate(rows):
            repr_row = list(rows[i:i + 1].render())[0]

            class_permission = permissions[row.id]
            enroll = class_permission.get('Enroll', '')
            shopbook = class_permission.get('ShopBook', '')
            attend = class_permission.get('Attend', '')

            if enroll:
                enroll = green_check

            if shopbook:
                shopbook = green_check

            if attend:
                attend = green_check

            tr = TR(TD(repr_row.Week_day),
                    TD(repr_row.Starttime, ' - ', repr_row.Endtime),
                    TD(repr_row.school_locations_id),
                    TD(repr_row.school_classtypes_id),
                    TD(enroll),
                    TD(shopbook),
                    TD(attend))

            table.append(tr)

        return table



    def get_class_permissions(self, public_only=True, formatted=False):
        '''
            :return: return list of class permissons (clsID: enroll, book in shop, attend)
        '''
        db = current.db

        # get groups for subscription
        query = (db.school_subscriptions_groups_subscriptions.school_subscriptions_id == self.ssuID)
        rows = db(query).select(db.school_subscriptions_groups_subscriptions.school_subscriptions_groups_id)

        group_ids = []
        for row in rows:
            group_ids.append(row.school_subscriptions_groups_id)

        # get permissions for subscription group
        left = [db.classes.on(db.classes_school_subscriptions_groups.classes_id == db.classes.id)]
        query = (db.classes_school_subscriptions_groups.school_subscriptions_groups_id.belongs(group_ids))

        if public_only:
            query &= (db.classes.AllowAPI == True)

        rows = db(query).select(db.classes_school_subscriptions_groups.ALL,
                                left=left)

        permissions = {}
        for row in rows:
            clsID = row.classes_id
            if clsID not in permissions:
                permissions[clsID] = {}

            if row.Enroll:
                permissions[clsID]['Enroll'] = True
            if row.ShopBook:
                permissions[clsID]['ShopBook'] = True
            if row.Attend:
                permissions[clsID]['Attend'] = True

        if not formatted:
            return permissions
        else:
            return self._get_class_permissions_format(permissions)

    
class Class:
    """
        Class that gathers useful functions for a class in OpenStudio
    """
    def __init__(self, clsID, date):
        self.clsID = clsID
        self.date = date

        db = current.db
        self.cls = db.classes(self.clsID)


    def get_name(self, pretty_date=False):
        """
            Returns class name formatted for general use
        """
        db = current.db
        T = current.T
        TIME_FORMAT = current.TIME_FORMAT
        DATE_FORMAT = current.DATE_FORMAT

        if pretty_date:
            date = self.date.strftime('%d %B %Y')
        else:
            date = self.date.strftime(DATE_FORMAT)


        record = self.cls
        location = db.school_locations[record.school_locations_id].Name
        classtype = db.school_classtypes[record.school_classtypes_id].Name
        class_name =  date + ' ' + \
                      record.Starttime.strftime(TIME_FORMAT) + ' - ' + \
                      classtype + ' ' + location

        return class_name


    def get_name_shop(self):
        '''
            Returns class name formatted for use in customer profile and shop
        '''
        db = current.db
        T = current.T
        TIME_FORMAT = current.TIME_FORMAT

        record = self.cls
        location = db.school_locations[record.school_locations_id].Name
        classtype = db.school_classtypes[record.school_classtypes_id].Name
        class_name =  self.date.strftime('%d %B %Y') + ' ' + '<br><small>' + \
                      record.Starttime.strftime(TIME_FORMAT) + ' - ' + \
                      record.Endtime.strftime(TIME_FORMAT) + ' ' + \
                      classtype + ' ' + \
                      T('in') + ' ' + location + '</small>'

        return class_name


    def get_prices(self):
        """
            Returns the price for a class
        """
        db = current.db

        query = (db.classes_price.classes_id == self.clsID) & \
                (db.classes_price.Startdate <= self.date) & \
                ((db.classes_price.Enddate >= self.date) |
                 (db.classes_price.Enddate == None))
        prices = db(query).select(db.classes_price.ALL,
                                  orderby=db.classes_price.Startdate)

        if prices:
            prices = prices.first()
            dropin = prices.Dropin or 0
            trial  = prices.Trial or 0
            dropin_membership = prices.DropinMembership or 0
            trial_membership = prices.TrialMembership or 0

            trial_tax = db.tax_rates(prices.tax_rates_id_trial)
            dropin_tax = db.tax_rates(prices.tax_rates_id_dropin)
            trial_tax_membership = db.tax_rates(prices.tax_rates_id_trial_membership)
            dropin_tax_membership = db.tax_rates(prices.tax_rates_id_dropin_membership)

            try:
                trial_tax_rates_id    = trial_tax.id
                dropin_tax_rates_id   = dropin_tax.id
                trial_tax_percentage  = trial_tax.Percentage
                dropin_tax_percentage = dropin_tax.Percentage
            except AttributeError:
                trial_tax_rates_id    = None
                dropin_tax_rates_id   = None
                trial_tax_percentage  = None
                dropin_tax_percentage = None

            try:
                trial_tax_rates_id_membership = trial_tax_membership.id
                dropin_tax_rates_id_membership = dropin_tax_membership.id
                trial_tax_percentage_membership = trial_tax_membership.Percentage
                dropin_tax_percentage_membership = dropin_tax_membership.Percentage
            except AttributeError:
                trial_tax_rates_id_membership = None
                dropin_tax_rates_id_membership = None
                trial_tax_percentage_membership = None
                dropin_tax_percentage_membership= None

        else:
            dropin = 0
            trial  = 0
            trial_tax_rates_id    = None
            dropin_tax_rates_id   = None
            trial_tax_percentage  = None
            dropin_tax_percentage = None
            dropin_membership = 0
            trial_membership = 0
            trial_tax_rates_id_membership = None
            dropin_tax_rates_id_membership = None
            trial_tax_percentage_membership = None
            dropin_tax_percentage_membership = None


        return dict(
            trial  = trial,
            dropin = dropin,
            trial_tax_rates_id   = trial_tax_rates_id,
            dropin_tax_rates_id   = dropin_tax_rates_id,
            trial_tax_percentage  = trial_tax_percentage,
            dropin_tax_percentage = dropin_tax_percentage,
            trial_membership = trial_membership,
            dropin_membership = dropin_membership,
            trial_tax_rates_id_membership = trial_tax_rates_id_membership,
            dropin_tax_rates_id_membership = dropin_tax_rates_id_membership,
            trial_tax_percentage_membership = trial_tax_percentage_membership,
            dropin_tax_percentage_membership = dropin_tax_percentage_membership,
        )


    def get_prices_customer(self, cuID):
        """
            Returns the price for a class
            :param cuID: db.auth_user.id
            :return: dict of class prices
        """
        from openstudio.os_customer import Customer

        db = current.db
        customer = Customer(cuID)
        has_membership = customer.has_membership_on_date(self.date)


        query = (db.classes_price.classes_id == self.clsID) & \
                (db.classes_price.Startdate <= self.date) & \
                ((db.classes_price.Enddate >= self.date) |
                 (db.classes_price.Enddate == None))
        prices = db(query).select(db.classes_price.ALL,
                                  orderby=db.classes_price.Startdate)

        if prices:
            prices = prices.first()

            if not has_membership:
                dropin = prices.Dropin or 0
                trial = prices.Trial or 0

                trial_tax = db.tax_rates(prices.tax_rates_id_trial)
                dropin_tax = db.tax_rates(prices.tax_rates_id_dropin)

                try:
                    trial_tax_rates_id = trial_tax.id
                    dropin_tax_rates_id = dropin_tax.id
                    trial_tax_percentage = trial_tax.Percentage
                    dropin_tax_percentage = dropin_tax.Percentage
                except AttributeError:
                    trial_tax_rates_id = None
                    dropin_tax_rates_id = None
                    trial_tax_percentage = None
                    dropin_tax_percentage = None
            else: # has membership
                dropin = prices.DropinMembership or 0
                trial = prices.TrialMembership or 0

                trial_tax = db.tax_rates(prices.tax_rates_id_trial_membership)
                dropin_tax = db.tax_rates(prices.tax_rates_id_dropin_membership)

                try:
                    trial_tax_rates_id = trial_tax.id
                    dropin_tax_rates_id = dropin_tax.id
                    trial_tax_percentage = trial_tax.Percentage
                    dropin_tax_percentage = dropin_tax.Percentage
                except AttributeError:
                    trial_tax_rates_id = None
                    dropin_tax_rates_id = None
                    trial_tax_percentage = None
                    dropin_tax_percentage = None

        else:
            dropin = 0
            trial  = 0
            trial_tax_rates_id    = None
            dropin_tax_rates_id   = None
            trial_tax_percentage  = None
            dropin_tax_percentage = None


        return dict(
            trial  = trial,
            dropin = dropin,
            trial_tax_rates_id   = trial_tax_rates_id,
            dropin_tax_rates_id   = dropin_tax_rates_id,
            trial_tax_percentage  = trial_tax_percentage,
            dropin_tax_percentage = dropin_tax_percentage,
        )


    def get_full(self):
        '''
            Check whether or not this class is full
        '''
        db = current.db

        spaces = self.cls.Maxstudents

        query = (db.classes_attendance.classes_id == self.clsID) & \
                (db.classes_attendance.ClassDate == self.date) & \
                (db.classes_attendance.BookingStatus != 'cancelled')
        filled = db(query).count()

        full = True if filled >= spaces else False

        return full


    def get_full_bookings_shop(self):
        '''
            Check whether there are spaces left for online bookings
        '''
        db = current.db

        spaces = self.cls.MaxOnlineBooking
        query = (db.classes_attendance.classes_id == self.clsID) & \
                (db.classes_attendance.ClassDate == self.date) & \
                (db.classes_attendance.online_booking == True) & \
                (db.classes_attendance.BookingStatus != 'cancelled')
        filled = db(query).count()

        full = True if filled >= spaces else False

        return full


    def get_invoice_order_description(self, attendance_type):
        '''        
            :return: string with a description of the class 
        '''
        DATE_FORMAT = current.DATE_FORMAT
        TIME_FORMAT = current.TIME_FORMAT

        db = current.db
        T  = current.T

        prices = self.get_prices()
        if attendance_type == 1:
            price = prices['trial']
            tax_rates_id = prices['trial_tax_rates_id']
            at = T('Trial')
        elif attendance_type == 2:
            price = prices['dropin']
            tax_rates_id = prices['dropin_tax_rates_id']
            at = T('Drop in')


        location =  db.school_locations(self.cls.school_locations_id)
        classtype = db.school_classtypes(self.cls.school_classtypes_id)

        description = self.date.strftime(DATE_FORMAT) + ' ' + \
                      self.cls.Starttime.strftime(TIME_FORMAT) + ' ' + \
                      classtype.Name + ' ' + \
                      location.Name + ' ' + \
                      '(' + at + ')'

        return description


    def add_to_shoppingcart(self, cuID, attendance_type=2):
        """
            Add a workshop product to the shopping cart of a customer
            attendance_type can be 1 for trial class or 2 for drop in class
        """
        db = current.db

        db.customers_shoppingcart.insert(
            auth_customer_id = cuID,
            classes_id = self.clsID,
            ClassDate = self.date,
            AttendanceType = attendance_type
        )


    def is_on_correct_weekday(self):
        """
            Checks if self.date.isoweekday() == self.cls.Week_day
        """
        if self.date.isoweekday() == self.cls.Week_day:
            return True
        else:
            return False


    def is_past(self):
        """
            Return True if NOW_LOCAL > Class start else return False
        """
        import pytz

        db = current.db
        now = current.NOW_LOCAL
        TIMEZONE = current.TIMEZONE

        cls_time = self.cls.Starttime

        class_dt = datetime.datetime(year=self.date.year,
                                     month=self.date.month,
                                     day=self.date.day,
                                     hour=cls_time.hour,
                                     minute=cls_time.minute)
        # localize the class datetime so it can be compared to now
        # class_dt = pytz.utc.localize(class_dt)
        class_dt = pytz.timezone(TIMEZONE).localize(class_dt)

        if class_dt < now:
            return True
        else:
            return False


    def is_cancelled(self):
        """
            Return True if the class is cancelled, else return False
        """
        db = current.db
        query = (db.classes_otc.classes_id == self.clsID) & \
                (db.classes_otc.ClassDate == self.date) & \
                (db.classes_otc.Status == 'cancelled')

        cancelled = True if db(query).count() else False
        return cancelled


    def is_holiday(self):
        """
            Return True if the class is within a holiday, else return False
        """
        db = current.db

        # Query school_holidays table to see if there's a holiday for this location
        left = [db.school_holidays_locations.on(db.school_holidays.id ==
                                                db.school_holidays_locations.school_holidays_id)]
        query = (db.school_holidays.Startdate <= self.date) & \
                (db.school_holidays.Enddate >= self.date) & \
                (db.school_holidays_locations.school_locations_id == self.cls.school_locations_id)

        rows = db(query).select(db.school_holidays.id,
                                left=left)

        holiday = True if len(rows) else False
        return holiday


    def is_taking_place(self):
        """
             Check if the class is not in past, cancelled or in a holiday
             Return True if not in past, cancelled or in holiday, else return False
        """
        correct_weekday = self.is_on_correct_weekday()
        past = self.is_past()
        cancelled = self.is_cancelled()
        holiday = self.is_holiday()

        if not past and not cancelled and not holiday and correct_weekday:
            return True
        else:
            return False


    def is_booked_by_customer(self, cuID):
        """
        :param cuID: db.auth_user.id
        :return: Boolean

        Check if the class is booked by this customer or not
        """
        db = current.db

        query = ((db.classes_attendance.BookingStatus == 'booked') |
                 (db.classes_attendance.BookingStatus == 'attending')) & \
                (db.classes_attendance.classes_id == self.clsID) & \
                (db.classes_attendance.ClassDate == self.date) & \
                (db.classes_attendance.auth_customer_id == cuID)

        rows = db(query).select(db.classes_attendance.id)
        if len(rows) > 0:
            return True
        else:
            return False


    def has_recurring_reservation_spaces(self):
        '''
        Check whether a class has space for more recurring reservations
        :param date: datetime.date
        :return: Boolean
        '''
        db = current.db

        spaces = self.cls.MaxReservationsRecurring

        query = (db.classes_reservation.classes_id == self.clsID) & \
                (db.classes_reservation.ResType == 'recurring') & \
                (db.classes_reservation.Startdate <= self.date) & \
                ((db.classes_reservation.Enddate >= self.date) |
                 (db.classes_reservation.Enddate == None))

        reservations = db(query).count()

        if reservations >= spaces:
            return False
        else:
            return True


    def get_trialclass_allowed_in_shop(self):
        """
        Check whether trial classes in the shop are allowed or not
        :return: Boolean
        """
        if self.cls.AllowShopTrial:
            return True
        else:
            return False


class ClassReservationHelper:
    '''
        This class collects functions classes_reservation that can return or modify multple records at once
    '''
    def get_recurring_reservations_on_date(self, date, by_class=False):
        '''
        :param date: datetime.date
        :return: rows of all recurring reservations on a given date
        '''
        db = current.db

        query = (db.classes_reservation.Startdate <= date) & \
                ((db.classes_reservation.Enddate >= date) |
                 (db.classes_reservation.Enddate == None)) & \
                (db.classes_reservation.ResType == 'recurring')

        return db(query).select(db.classes_reservation.ALL)


class ClassAttendance:
    '''
        This class collects functions related to a class attendance record
    '''
    def __init__(self, clattID):
        db = current.db
        self.id = clattID
        self.row = db.classes_attendance(clattID)


    def get_datetime_start(self):
        '''
            Returns datetime object of class start
        '''
        db = current.db

        pytz = current.globalenv['pytz']
        TIMEZONE = 'Etc/UTC' # Class times in DB be considered local and shouldn't have extra hours added / subtracted

        cls = db.classes(self.row.classes_id)
        date = self.row.ClassDate
        dt_start = datetime.datetime(date.year,
                                     date.month,
                                     date.day,
                                     int(cls.Starttime.hour),
                                     int(cls.Starttime.minute))
        dt_start = pytz.utc.localize(dt_start).astimezone(pytz.timezone(TIMEZONE))

        return dt_start


    def get_cancel_before(self):
        '''
            Calculates datetime of latest cancellation possibility
        '''
        import math
        db = current.db

        cls = db.classes(self.row.classes_id)
        date = self.row.ClassDate

        get_sys_property = current.globalenv['get_sys_property']

        shop_classes_cancellation_limit = get_sys_property('shop_classes_cancellation_limit') or 0


        dt_start = self.get_datetime_start()
        delta = datetime.timedelta(hours=int(shop_classes_cancellation_limit))

        return dt_start - delta


    def get_cancellation_possible(self):
        '''
             Can we still cancel this booking?
             Allow cancellation when within the configures hours limit and not already attending
        '''
        NOW_LOCAL = current.NOW_LOCAL
        cancel_before = self.get_cancel_before()

        if NOW_LOCAL < cancel_before and not self.row.BookingStatus == 'attending':
            return True
        else:
            return False


    def set_status_cancelled(self, force=False):
        '''
            Set status cancelled
        '''
        T = current.T
        db = current.db
        NOW_LOCAL = current.NOW_LOCAL
        return_message = T('Cancelled class')

        # check hours in advance policy
        if self.get_cancellation_possible() or force:
            # Set booking status to cancelled
            self.row.BookingStatus = 'cancelled'
            self.row.update_record()

            # Remove credits taken from customer for attending a class
            query = (db.customers_subscriptions_credits.classes_attendance_id == self.id)
            db(query).delete()
        else:
            return_message = T("This class can no longer be cancelled")

        return return_message


class AttendanceHelper:
    '''
        This class collects common function for attendance in OpenStudio
    '''
    # def get_attending(self, clsID, date, cuID):
    #     '''
    #         Returns wheter or not a customer is attending a class
    #     '''
    #     db = current.db
    #
    #     attending = db.classes_attendance(classes_id       = clsID,
    #                                       ClassDate        = date,
    #                                       auth_customer_id = cuID)
    #
    #     if attending:
    #         return_value = attending
    #     else:
    #         return_value = False
    #
    #     return return_value


    # def get_attending_list(self, clsID, date):
    #     '''
    #         Return list of customers attending a class as list of
    #         db.auth_user.id
    #     '''
    #     db = current.db
    #
    #     query = (db.classes_attendance.classes_id == clsID) & \
    #             (db.classes_attendance.ClassDate  == date)
    #
    #     rows = db(query).select(db.classes_attendance.auth_customer_id)
    #     attending = []
    #     for row in rows:
    #         if not row.auth_customer_id in attending:
    #             attending.append(row.auth_customer_id)
    #
    #     return attending


    def get_attendance_rows(self, clsID, date):
        '''
            :param clsID: db.classes.db
            :param date: class date
            :return: attendance rows
        '''
        db = current.db

        filter_date_teacher_notes = date - datetime.timedelta(days=92)

        fields = [
            db.auth_user.id,
            db.auth_user.trashed,
            db.auth_user.birthday,
            db.auth_user.thumbsmall,
            db.auth_user.first_name,
            db.auth_user.last_name,
            db.auth_user.display_name,
            db.auth_user.email,
            db.classes_reservation.id,
            db.classes_reservation.ResType,
            db.classes_reservation.Startdate,
            db.classes_reservation.Enddate,
            db.invoices.id,
            db.invoices.InvoiceID,
            db.invoices.Status,
            db.invoices.payment_methods_id,
            db.classes_attendance.id,
            db.classes_attendance.AttendanceType,
            db.classes_attendance.online_booking,
            db.classes_attendance.BookingStatus,
            db.classes_attendance.CreatedOn,
            db.auth_user.teacher_notes_count,  # Holds count of recent teacher notes
            db.auth_user.teacher_notes_count_injuries
        ]

        query = '''
            SELECT au.id,
                   au.trashed,
                   au.birthday,
                   au.thumbsmall,
                   au.first_name,
                   au.last_name,
                   au.display_name,
                   au.email, 
                   clr.id,
                   clr.restype,
                   clr.Startdate,
                   clr.Enddate,
                   inv.id,
                   inv.InvoiceID,
                   inv.Status,
                   inv.payment_methods_id,
                   clatt.id,
                   clatt.AttendanceType,
                   clatt.online_booking,
                   clatt.BookingStatus,
                   clatt.CreatedOn,
                   ( SELECT COUNT(*) FROM customers_notes cn 
                     WHERE cn.TeacherNote = 'T' AND 
                           cn.auth_customer_id = au.id AND
                           cn.NoteDate >= '{filter_date_teacher_notes}' ),
                   ( SELECT COUNT(*) FROM customers_notes cn 
                     WHERE cn.TeacherNote = 'T' AND 
                           cn.auth_customer_id = au.id AND
                           cn.Injury = 'T' )
            FROM auth_user au
            LEFT JOIN
                ( SELECT id,
                         auth_customer_id,
                         AttendanceType,
                         online_booking,
                         BookingStatus,
                         CreatedOn
                  FROM classes_attendance
                  WHERE ClassDate = '{date}' AND classes_id = {clsID} ) clatt
                ON clatt.auth_customer_id = au.id
            LEFT JOIN
                ( SELECT id,
                         auth_customer_id,
                         classes_id,
                         Startdate,
                         Enddate,
                         ResType,
                         TrialClass
                  FROM classes_reservation
                  WHERE classes_id = {clsID} AND
                        Startdate <= '{date}' AND
                        (Enddate >= '{date}' or Enddate IS NULL)) clr
                ON clr.auth_customer_id = au.id
            LEFT JOIN
                invoices_classes_attendance ica
                ON ica.classes_attendance_id = clatt.id
            LEFT JOIN
                invoices inv ON ica.invoices_id = inv.id
            WHERE clatt.id IS NOT NULL
            ORDER BY au.display_name
        '''.format(date  = date,
                   filter_date_teacher_notes = filter_date_teacher_notes,
                   clsID = clsID)

        rows = db.executesql(query, fields=fields)

        return rows


    def get_attendance_rows_past_days(self, clsID, date, days):
        '''
            :param clsID: db.classes.id 
            :param date: datetime.date
            :param days: int
            :return: 
        '''
        db = current.db
        cache = current.cache

        cls = Class(clsID, date)

        delta = datetime.timedelta(days=days)
        x_days_ago = date - delta

        left = [ db.classes.on(db.classes_attendance.classes_id ==
                               db.classes.id),
                 db.auth_user.on(db.classes_attendance.auth_customer_id ==
                                 db.auth_user.id) ]

        query = (db.classes.school_classtypes_id == cls.cls.school_classtypes_id) & \
                (db.classes.school_locations_id == cls.cls.school_locations_id) & \
                (db.classes_attendance.classes_id == clsID) & \
                (db.classes_attendance.ClassDate <= date) & \
                (db.classes_attendance.ClassDate >= x_days_ago) & \
                (db.auth_user.trashed == False) & \
                (db.auth_user.customer == True)


        rows = db(query).select(db.auth_user.id,
                                db.auth_user.trashed,
                                db.auth_user.birthday,
                                db.auth_user.thumbsmall,
                                db.auth_user.first_name,
                                db.auth_user.last_name,
                                db.auth_user.display_name,
                                db.auth_user.email,
                                db.classes.school_classtypes_id,
                                left=left,
                                orderby=db.auth_user.display_name,
                                distinct=True,
                                cache=(cache.ram, 30))

        return rows


    def get_reservation_rows(self, clsID, date):
        """
            :param clsID: db.classes.id 
            :param date: datetime.date
            :return: reservation rows for a class
        """
        db = current.db

        fields = [
            db.auth_user.id,
            db.auth_user.trashed,
            db.auth_user.birthday,
            db.auth_user.thumbsmall,
            db.auth_user.first_name,
            db.auth_user.last_name,
            db.auth_user.display_name,
            db.auth_user.email,
            db.classes_reservation.id,
            db.classes_reservation.ResType,
            db.classes_reservation.Startdate,
            db.classes_reservation.Enddate,
        ]

        query = '''
            SELECT au.id,
                   au.trashed,
                   au.birthday,
                   au.thumbsmall,
                   au.first_name,
                   au.last_name,
                   au.display_name,
                   au.email,
                   clr.id,
                   clr.restype,
                   clr.Startdate,
                   clr.Enddate
            FROM auth_user au
            LEFT JOIN
                ( SELECT id,
                         auth_customer_id
                  FROM classes_attendance
                  WHERE ClassDate = '{date}' AND classes_id = {clsID} ) clatt
                ON clatt.auth_customer_id = au.id
            LEFT JOIN
                ( SELECT id,
                         auth_customer_id,
                         classes_id,
                         Startdate,
                         Enddate,
                         ResType,
                         TrialClass
                  FROM classes_reservation
                  WHERE Startdate <= '{date}' AND
                        (Enddate >= '{date}' or Enddate IS NULL)) clr
                ON clr.auth_customer_id = au.id
            WHERE clr.classes_id = '{clsID}'
            ORDER BY clr.TrialClass DESC, au.display_name
        '''.format(date  = date,
                   clsID = clsID)

        rows = db.executesql(query, fields=fields)

        return rows


    def get_attending_list_between(self,
                                   start_date,
                                   end_date):
        """
            Returns distincs a list of customers attending any classes between start_date
            and end_date as a list of db.auth_user_id
        """
        db = current.db

        left = [ db.auth_user.on(db.classes_attendance.auth_customer_id == db.auth_user.id) ]

        query = (db.classes_attendance.ClassDate >= start_date) & \
                (db.classes_attendance.ClassDate <= end_date) & \
                ((db.classes_attendance.AttendanceType == None) |
                 (db.classes_attendance.AttendanceType == 3))

        rows = db(query).select(db.classes_attendance.auth_customer_id,
                                distinct=True,
                                left=left,
                                orderby=db.auth_user.display_name)

        attending = []
        for row in rows:
            attending.append(row.auth_customer_id)

        return attending


    def get_last_attendance(self, customer_ids):
        """
            For each customer id returns the date when the customer last attended
            a class. Returns a dictionary where the key is the customer id and the
            value is the last date when the customer attended a class.

            :param customer_ids: the customers to check
        """
        db = current.db
        max = db.classes_attendance.ClassDate.max()
        having_query = (db.classes_attendance.auth_customer_id.belongs(customer_ids))
        rows = db().select(db.classes_attendance.auth_customer_id,
            max,
            groupby=db.classes_attendance.auth_customer_id,
            having=having_query)

        last_dates = {}
        for row in rows:
            last_dates[row.classes_attendance.auth_customer_id] = row[max]

        return last_dates


    def get_checkin_list_customers_booked(self,
                                          clsID,
                                          date,
                                          class_full=False,
                                          pictures=True,
                                          reservations=True,
                                          invoices=True,
                                          show_notes=True,
                                          show_booking_time=True,
                                          show_subscriptions=True,
                                          manage_checkin=True):
        '''
            :param clsID: db.classes.id
            :param date: Class date
            :return: Table of customers checked in for this class
        '''
        def add_table_row(row,
                          repr_row,
                          pictures=pictures,
                          #manual_enabled=False,
                          #this_class=False,
                          reservations=reservations,
                          show_subscriptions=show_subscriptions,
                          invoices=invoices,
                          show_notes=show_notes,
                          show_booking_time=show_booking_time,
                          #class_full=False
                          ):
            ''''
                Adds a row to the table
            '''
            cuID = row.auth_user.id

            customer = Customer(cuID)
            subscr_cards = ''
            if show_subscriptions:
                subscr_cards = customer.get_subscriptions_and_classcards_formatted(
                    date,
                    new_cards=False,
                    show_subscriptions=show_subscriptions,
                    )

            # check attendance
            if row.classes_attendance.BookingStatus == 'attending':
                links = []
                # Check update permission
                if (auth.has_membership(group_id='Admins') or
                    auth.has_permission('update', 'classes_attendance')):
                    links = [['header', T('Booking status')]]
                    links.append(A(os_gui.get_fa_icon('fa-check-circle-o'),
                                   T('Booked'), ' ',
                                   _href=URL('classes', 'attendance_set_status',
                                             vars={'clattID':row.classes_attendance.id,
                                                   'status':'booked'}),
                                   _class="text-blue"))
                    links.append(A(os_gui.get_fa_icon('fa-ban'),
                                   T('Cancelled'), ' ',
                                   _href=URL('classes', 'attendance_set_status',
                                             vars={'clattID':row.classes_attendance.id,
                                                   'status':'cancelled'}),
                                   _class="text-yellow"))

                # Check delete permission
                if (auth.has_membership(group_id='Admins') or
                    auth.has_permission('delete', 'classes_attendance')):
                    delete_onclick = "return confirm('" + \
                              T('Do you really want to remove this booking?') + "');"

                    links.append('divider')
                    links.append(A(os_gui.get_fa_icon('fa-minus-circle'),
                                   T('Remove'), ' ',
                                   _href=URL('classes', 'attendance_remove', vars={'clattID':row.classes_attendance.id}),
                                   _onclick=delete_onclick,
                                   _class="text-red"))

                btn = os_gui.get_dropdown_menu(
                    links=links,
                    btn_text=T('Actions'),
                    btn_size='btn-sm',
                    btn_icon='actions',
                    menu_class='btn-group pull-right')

                # btn = DIV(_class='btn-group pull-right')
                attending = SPAN(_class='glyphicon glyphicon-ok green very_big_check')


            else:
                attending = SPAN(_class='glyphicon glyphicon-ok grey-light very_big_check')
                btn = ''
                # Check update permission
                if (auth.has_membership(group_id='Admins') or
                    auth.has_permission('update', 'classes_attendance')):

                    checkin = ''
                    if not class_full:
                        checkin = os_gui.get_button('noicon',
                                                    URL('classes', 'attendance_set_status',
                                                        vars={'clattID':row.classes_attendance.id,
                                                              'status':'attending'}),
                                                    title=T('Check in'))

                    links = [['header', T('Booking status')]]
                    links.append(A(os_gui.get_fa_icon('fa-ban'),
                                   T('Cancelled'), ' ',
                                   _href=URL('classes', 'attendance_set_status',
                                             vars={'clattID':row.classes_attendance.id,
                                                   'status':'cancelled'}),
                                   _class="text-yellow"))

                # Check delete permission
                if (auth.has_membership(group_id='Admins') or
                        auth.has_permission('delete', 'classes_attendance')):
                    delete_onclick = "return confirm('" + \
                                     T('Do you really want to remove this booking?') + "');"

                    links.append('divider')
                    links.append(A(os_gui.get_fa_icon('fa-minus-circle'),
                                   T('Remove'), ' ',
                                   _href=URL('classes', 'attendance_remove',
                                             vars={'clattID': row.classes_attendance.id}),
                                   _onclick=delete_onclick,
                                   _class="text-red"))

                dropdown = os_gui.get_dropdown_menu(
                    links=links,
                    btn_text='',
                    btn_size='btn-sm',
                    btn_icon='actions',
                    menu_class='btn-group pull-right')


                if not manage_checkin:
                    # Remove additional options on check-in button for self checkin
                    btn = DIV(checkin, _class='pull-right')
                else:
                    btn = DIV(checkin, dropdown, _class='btn-group pull-right')


                # if not class_full:
                # btn = self.get_signin_buttons(clsID,
                #                               date,
                #                               cuID,
                #                               manual_enabled=manual_enabled)
                # else:
                #     btn = ''

            # Customer picture
            td_pic = ''
            if pictures:
                td_pic = TD(repr_row.auth_user.thumbsmall,
                            _class='os-customer_image_td hidden-xs')


            td_labels = TD(repr_row.classes_attendance.BookingStatus, _class='hidden-xs')
            if reservations and row.classes_reservation.id:
                date_formatted = date.strftime(DATE_FORMAT)
                crID = row.classes_reservation.id

                td_labels.append(SPAN(' ', repr_row.classes_reservation.ResType))

                try:
                    if row.classes_attendance.AttendanceType == 1:
                        td_labels.append(' ')
                        td_labels.append(os_gui.get_label('success', T('Trial class')))

                    elif row.classes_attendance.AttendanceType == 2:
                        td_labels.append(' ')
                        td_labels.append(os_gui.get_label('primary', T('Drop in')))
                except AttributeError:
                    pass


            if show_booking_time:
                td_labels.append(BR())
                td_labels.append(SPAN(T('Booked on'), ' ', repr_row.classes_attendance.CreatedOn,
                                      _class='vsmall_font grey'))

            # Add a small label for online bookings
            try:
                if row.classes_attendance.online_booking:
                    td_labels.append(TD(os_gui.get_label('info', T('Online'))))
            except AttributeError:
                pass


            ##
            # Invoice for drop in or trial class
            ##
            td_inv = ''
            if invoices:
                invs = Invoices()
                if row.invoices.id:
                    invoice = ih.represent_invoice_for_list(
                        row.invoices.id,
                        repr_row.invoices.InvoiceID,
                        repr_row.invoices.Status,
                        row.invoices.Status,
                        row.invoices.payment_methods_id
                    )
                else:
                    invoice = ''

                td_inv = TD(invoice)

            ##
            # Link to notes page
            ##
            link_notes = ''
            if show_notes:
                notes_text = T('notes')
                if row.auth_user.teacher_notes_count == 1:
                    notes_text = T('note')
                notes_link_text = SPAN(row.auth_user.teacher_notes_count, ' ', T('Recent'), ' ', notes_text)

                count_injuries = row.auth_user.teacher_notes_count_injuries
                if count_injuries > 0:
                    injuries_text = T('Injuries')
                    if count_injuries == 1:
                        injuries_text = T('Injury')
                    notes_link_text.append(BR())
                    notes_link_text.append(SPAN(count_injuries, ' ', injuries_text, _class='smaller_font text-red bold'))

                link_notes = SPAN(A(notes_link_text,
                                    _href=URL('classes', 'attendance_teacher_notes',
                                              vars={'cuID':row.auth_user.id,
                                                    'clsID':clsID,
                                                    'date':date.strftime(DATE_FORMAT)})))

            # TD('notes', row.auth_user.eetra_field_intxtra_field_int),

            tr = TR(TD(attending, _class='very_big_check'),
                    td_pic,
                    TD(SPAN(row.auth_user.display_name, _class='bold'), BR(),
                       subscr_cards),
                    td_labels,
                    td_inv,
                    TD(link_notes),
                    btn)

            table.append(tr)

        ##
        # Start main function
        ##
        T = current.T
        db = current.db
        auth = current.auth
        os_gui = current.globalenv['os_gui']
        DATE_FORMAT = current.DATE_FORMAT

        modals = DIV()

        cls = db.classes(clsID)

        header = THEAD(TR(TH(),
                          TH(),
                          TH(T('Customer')),
                          TH(T('Status')), # Booking Status [and Enrollment]
                          TH(),
                          TH(),
                          TH()))

        rows = self.get_attendance_rows(clsID, date)
        table = TABLE(header, _class='table table-striped table-hover')

        for i, row in enumerate(rows):
            #print row
            repr_row = list(rows[i:i+1].render())[0]
            add_table_row(row,
                          repr_row,
                          reservations=reservations,
                          show_subscriptions=show_subscriptions,
                          invoices=invoices,
                          show_notes=show_notes,
                          show_booking_time=show_booking_time)

        return table


    def get_checkin_list_customers(self,
                                   clsID,
                                   date,
                                   pictures=False,
                                   manual_enabled=False,
                                   this_class=False,
                                   reservations=False,
                                   reservations_cancel=False,
                                   subscriptions=True,
                                   invoices=False,
                                   show_notes=False,
                                   class_full=False):
        '''
            Returns a list of customers who have a reservation or have attended
            a class of this type in the past month

            this_class
            True: look for attendance for this class in the past month
            False: look for attendance for this classtype in the past month
        '''
        def add_table_row(row,
                          repr_row,
                          reservations=False,
                          invoices=False,
                          show_notes=False,
                          modals=None):
            ''''
                Adds a row to the table
            '''
            cuID = row.auth_user.id

            customer = Customer(cuID)
            subscr_cards = customer.get_subscriptions_and_classcards_formatted(
                date,
                new_cards=False,
                show_subscriptions=subscriptions,
                )

            # check attendance
            if cuID in attendance_list:
                btn = DIV(_class='btn-group pull-right')
                attending = SPAN(_class='glyphicon glyphicon-ok green very_big_check')
                date_formatted = date.strftime(DATE_FORMAT)

                notes = ''
                notes_perm = auth.has_membership(group_id='Admins') or \
                             auth.has_permission('read', 'customers_notes_teachers')
                if show_notes and notes_perm:
                    result = self._get_teachers_note_modal(customer.row.id,
                                                           customer.row.display_name,
                                                           modals)
                    modals = result['modals_div']
                    btn.append(result['button'])

                onclick = "return confirm('" + \
                          T('Really check out?') + "');"
                remove = os_gui.get_button('delete_notext',
                                           URL('classes', 'attendance_remove',
                                               vars={'clsID': clsID,
                                                     'cuID': cuID,
                                                     'date': date_formatted}),
                                           title=T('Cancel'),
                                           btn_class='btn-danger',
                                           btn_size='',
                                           onclick=onclick)
                btn.append(remove)


            else:
                attending = SPAN(_class='glyphicon glyphicon-ok grey-light very_big_check')
                if not class_full:
                    btn = self.get_signin_buttons(clsID,
                                                  date,
                                                  cuID,
                                                  manual_enabled=manual_enabled)
                else:
                    btn = ''

            # Customer picture
            td_pic = ''
            if pictures:
                td_pic = TD(repr_row.auth_user.thumbsmall,
                            _class='os-customer_image_td hidden-xs')

            td_res = ''
            if reservations and row.classes_reservation.id:
                date_formatted = date.strftime(DATE_FORMAT)
                crID = row.classes_reservation.id

                td_res = TD(repr_row.classes_reservation.ResType, _class='hidden-xs')

            td_atttype = ''
            try:
                td_atttype = TD()
                if row.classes_attendance.AttendanceType == 1:
                    td_atttype.append(os_gui.get_label('success', T('Trial class')))

                elif row.classes_attendance.AttendanceType == 2:
                    td_atttype.append(os_gui.get_label('primary', T('Drop in')))
            except AttributeError:
                pass

            # Add a small label for online bookings
            td_online_booking = ''
            try:
                if row.classes_attendance.online_booking:
                    td_online_booking = TD(os_gui.get_label('info', T('Online')))
            except AttributeError:
                pass


            td_inv = ''
            if invoices:
                invs = Invoices()
                if row.invoices.id:
                    invoice = ih.represent_invoice_for_list(
                        row.invoices.id,
                        repr_row.invoices.InvoiceID,
                        repr_row.invoices.Status,
                        row.invoices.Status,
                        row.invoices.payment_methods_id
                    )
                else:
                    invoice = ''

                td_inv = TD(invoice)


            tr = TR(TD(attending, _class='very_big_check'),
                    td_pic,
                    TD(SPAN(row.auth_user.display_name, _class='bold'), BR(),
                       subscr_cards),
                    td_res,
                    td_atttype,
                    td_online_booking,
                    td_inv,
                    btn)

            table.append(tr)

        # Set some values from the globalenv
        T = current.T
        db = current.db
        auth = current.auth
        os_gui = current.globalenv['os_gui']
        DATE_FORMAT = current.DATE_FORMAT

        modals = DIV()

        cls = db.classes(clsID)

        header = THEAD(TR(TH(),
                          TH(),
                          TH(),
                          TH(), # Enrollment
                          TH(),
                          TH()))


        table = TABLE(header,
                      _class='table table-striped table-hover full-width')

        # ## get list of customers attending this class
        rows = self.get_attendance_rows(clsID, date)

        attendance_list = []
        for i, row in enumerate(rows):
            attendance_list.append(row.auth_user.id)

            repr_row = list(rows[i:i+1].render())[0]
            add_table_row(row,
                          repr_row,
                          reservations=True,
                          invoices=invoices,
                          show_notes=show_notes,
                          modals=modals)


        ## get list of reservations
        rows = self.get_reservation_rows(clsID, date)

        reservations_list = []
        for i, row in enumerate(rows):
            if row.auth_user.id in attendance_list:
                continue

            repr_row = list(rows[i:i+1].render())[0]
            add_table_row(row, repr_row, reservations=True)

            reservations_list.append(row.auth_user.id)


        ## get list of customers who have attended this class during the last 2 weeks
        rows = self.get_attendance_rows_past_days(clsID, date, days=15)

        for i, row in enumerate(rows):
            if row.auth_user.id in attendance_list:
                continue

            if row.auth_user.id in reservations_list:
                continue

            repr_row = list(rows[i:i+1].render())[0]
            add_table_row(row, repr_row, reservations=False)

        return DIV(table, modals)


    def get_checkin_list_customers_email_list(self, clsID, date, days=15):
        '''
            :param clsID: db.classes.is 
            :param date: datetime.date
            :param days: int
            :return: list containing email addresses for all people attending, with reservations or expected to attend
        '''
        # Set some values from the globalenv
        db = current.db

        mailing_list = []
        # ## get list of customers attending this class
        rows = self.get_attendance_rows(clsID, date)

        attendance_list = []
        for i, row in enumerate(rows):
            attendance_list.append(row.auth_user.id)

            mailing_list.append([row.auth_user.first_name, row.auth_user.last_name, row.auth_user.email])


        ## get list of reservations
        rows = self.get_reservation_rows(clsID, date)

        reservations_list = []
        for i, row in enumerate(rows):
            if row.auth_user.id in attendance_list:
                continue

            mailing_list.append([row.auth_user.first_name, row.auth_user.last_name, row.auth_user.email])

            reservations_list.append(row.auth_user.id)


        ## get list of customers who have attended this class during the last x days
        rows = self.get_attendance_rows_past_days(clsID, date, days=days)

        for i, row in enumerate(rows):
            if row.auth_user.id in attendance_list:
                continue

            if row.auth_user.id in reservations_list:
                continue

                mailing_list.append([row.auth_user.first_name, row.auth_user.last_name, row.auth_user.email])

        return mailing_list


    def get_checkin_list_customers_email_excel(self, clsID, date, days=15):
        '''
            :param clsID: db.classes.is 
            :param date: datetime.date
            :param days: int
            :return: cStringIO stream containing: 
                list containing email addresses for all people attending, with reservations or expected to attend
        '''
        T = current.T

        import cStringIO, openpyxl
        stream = cStringIO.StringIO()

        title = T('MailingList')
        wb = openpyxl.workbook.Workbook(write_only=True)
        ws = wb.create_sheet(title=title)

        header = [ "First name",
                   "Last name",
                   "Email" ]
        ws.append(header)

        mailing_list = self.get_checkin_list_customers_email_list(clsID, date, days)
        for row in mailing_list:
            ws.append(row)

        wb.save(stream)


        return stream


    def get_signin_buttons(self, clsID, date, cuID, manual_enabled=True):
        '''
            Returns sign in buttons for a class
        '''
        db = current.db
        os_gui = current.globalenv['os_gui']
        DATE_FORMAT = current.DATE_FORMAT
        date_formatted = date.strftime(DATE_FORMAT)

        customer = Customer(cuID)
        # set random id, used for modal classes
        random_id = unicode(int(random.random() * 1000000000000))

        li_link_class = 'btn btn-default btn-lg full-width'

        button = ''
        btn_group = DIV(_class='btn-group pull-right')
        modals = DIV()
        button_text = current.T('Check in')
        # check if not already added
        check = db.classes_attendance(auth_customer_id = cuID,
                                      classes_id       = clsID,
                                      ClassDate        = date)
        if not check:
            # check for subscription
            subscription = ''
            li_subscription = ''
            li_trial = ''
            li_dropin = ''

            rows = customer.get_subscriptions_on_date(date)
            if rows:
                subscription = rows.first()
                csID = subscription.customers_subscriptions.id
                subscription_url = URL('classes', 'attendance_sign_in_subscription',
                                       vars={'cuID'  : cuID,
                                             'clsID' : clsID,
                                             'csID'  : csID,
                                             'date'  : date_formatted})
                li_subscription = LI(A(SPAN(os_gui.get_fa_icon('fa-edit'), ' ', current.T('Subscription')),
                                        _href=subscription_url,
                                        _class=li_link_class))

            ## check for class card
            classcard = ''
            classcard_choose_url = URL('classes',
                                       'attendance_list_classcards',
                                        vars={'cuID'  : cuID,
                                              'clsID' : clsID,
                                              'date'  : date_formatted},
                                        extension='')
            # set default classcard li, which links to page with add button
            li_classcard = LI(A(SPAN(os_gui.get_fa_icon('fa-ticket'), ' ', current.T('Class card')),
                              _href=classcard_choose_url,
                              _class=li_link_class))


            rows = customer.get_classcards(date)
            if rows:
                classcard_count = len(rows)
                classcard = rows.first()
                ccdID = classcard.customers_classcards.id

                classcard_sign_in_url = URL('classes',
                                            'attendance_sign_in_classcard',
                                            vars={'cuID'  : cuID,
                                                  'clsID' : clsID,
                                                  'ccdID' : ccdID,
                                                  'date'  : date_formatted})

                if classcard_count == 1:
                    classcard_url = classcard_sign_in_url
                else: # more than 1 card, allow user to choose
                    classcard_url = classcard_choose_url

                li_classcard = LI(A(SPAN(os_gui.get_fa_icon('fa-ticket'), ' ', current.T('Class card')),
                                    _href=classcard_url,
                                    _class=li_link_class))


            dropin_url = URL('classes', 'attendance_sign_in_dropin',
                             vars={'cuID'  : cuID,
                                   'clsID' : clsID,
                                   'date'  : date_formatted})
            li_dropin = LI(A(SPAN(os_gui.get_fa_icon('fa-level-down'), ' ', current.T('Drop in class')),
                             _href=dropin_url,
                             _class=li_link_class))
            trial_url = URL('classes', 'attendance_sign_in_trialclass',
                             vars={'cuID'  : cuID,
                                   'clsID' : clsID,
                                   'date'  : date_formatted})
            li_trial = LI(A(SPAN(os_gui.get_fa_icon('fa-compass'), ' ', current.T('Trial class')),
                            _href=trial_url,
                            _class=li_link_class))

            if classcard and subscription:
                modal_content = UL(li_subscription,
                                   li_classcard,
                                   _class='check-in_options')
                modal_class   = 'modal_signin_' + random_id
                button_class  = 'btn btn-default btn-checkin'
                modal_title   = current.T('Check in on subscription or class card?')
                result = os_gui.get_modal(button_text   = button_text,
                                          button_class  = button_class,
                                          modal_title   = modal_title,
                                          modal_content = modal_content,
                                          modal_class   = modal_class)
                btn_group.append(result['button'])
                modals.append(result['modal'])
            elif subscription:
                 # subscription button
                button = A(
                    button_text,
                    _href=subscription_url,
                    _class='btn btn-default btn-checkin')
                btn_group.append(button)
            elif classcard:
                button = A(
                    button_text,
                    _href=classcard_url,
                    _class='btn btn-default btn-checkin')
                btn_group.append(button)
            else:
                # drop in or trial class?
                # classes_attendance customers_id & trialclass attendance type count
                message = SPAN(current.T('No subscription or classcard found for this date.'))
                message.append(' ')
                message.append(current.T("Available options:"))
                modal_content = DIV(message,
                                    BR(), BR(),
                                    UL(li_trial,
                                       li_dropin,
                                       _class='check-in_options'))
                modal_class   = 'modal_signin_' + random_id
                button_class  = 'btn btn-default btn-checkin'
                modal_title   = current.T('Sign in as trial class or drop in class?')
                result = os_gui.get_modal(button_text   = button_text,
                                          button_class  = button_class,
                                          modal_title   = modal_title,
                                          modal_content = modal_content,
                                          modal_class   = modal_class)
                btn_group.append(result['button'])
                modals.append(result['modal'])

            ### Button with modal for manual choice ###

            modal_content = UL(_class='check-in_options')
            if li_subscription:
                modal_content.append(li_subscription)
            if li_classcard:
                modal_content.append(li_classcard)
            if li_dropin:
                modal_content.append(li_dropin)
            if li_trial:
                modal_content.append(li_trial)

            modal_class = 'modal_signin_manual_' + random_id
            button_class = 'btn btn-default pull-right'
            button_text = XML(SPAN(_class='glyphicon glyphicon-edit'))
            modal_title = current.T('Manual check in')
            result = os_gui.get_modal(button_text   = button_text,
                                      button_class  = button_class,
                                      button_title  = current.T("Manual check in"),
                                      modal_title   = modal_title,
                                      modal_content = modal_content,
                                      modal_class   = modal_class)
            if manual_enabled:
                btn_group.append(result['button'])
                modals.append(result['modal'])


        return SPAN(btn_group, modals)


    def get_customer_class_booking_options(self,
                                           clsID,
                                           date,
                                           customer,
                                           trial=False,
                                           complementary=False,
                                           list_type='shop',
                                           controller=''):
        """
        :param clsID: db.classes.id
        :param date: datetime.date
        :param date_formatted: datetime.date object formatted with current.DATE_FORMAT
        :param customer: Customer object
        :param: list_type: [shop, attendance, selfcheckin]
        :return:
        """
        def classes_book_options_get_button_book(url):
            """
                Return book button for booking options
            """
            button_text = T('Book')
            if list_type == 'attendance' or list_type == 'selfcheckin':
                button_text = T('Check in')

            button_book = A(SPAN(button_text, ' ', os_gui.get_fa_icon('fa-chevron-right')),
                            _href=url,
                            _class='pull-right btn btn-link')

            return button_book

        T = current.T
        db = current.db
        os_gui = current.globalenv['os_gui']
        CURRSYM = current.globalenv['CURRSYM']
        DATE_FORMAT = current.DATE_FORMAT
        get_sys_property = current.globalenv['get_sys_property']

        date_formatted = date.strftime(DATE_FORMAT)

        options = DIV(_class='shop-classes-booking-options row')
        # subscriptions
        subscriptions = customer.get_subscriptions_on_date(date)
        if subscriptions:
            for subscription in subscriptions:
                csID = subscription.customers_subscriptions.id
                # Shop urls are the default for this function when no list_type has been specified
                # Check remaining credits
                credits_remaining = subscription.customers_subscriptions.CreditsRemaining or 0
                recon_classes = subscription.school_subscriptions.ReconciliationClasses
                # Create subscription object
                cs = CustomerSubscription(csID)

                if list_type == 'shop':
                    subscription_permission_check = not int(clsID) in cs.get_allowed_classes_booking(public_only=True)
                else:
                    subscription_permission_check = not int(clsID) in cs.get_allowed_classes_attend(public_only=False)

                if subscription_permission_check:
                    # Check book permission
                    button_book = os_gui.get_button('noicon',
                                                    URL('#'),
                                                    title=SPAN(T("Not allowed for this class")),
                                                    btn_class='btn-link',
                                                    _class='disabled pull-right grey')
                else:

                    if credits_remaining > (recon_classes * -1):
                        url = URL(controller, 'class_book', vars={'clsID': clsID,
                                                      'csID': csID,
                                                      'cuID': customer.row.id,
                                                      'date': date_formatted})
                        button_book = classes_book_options_get_button_book(url)
                    else:
                        button_book = os_gui.get_button('noicon',
                                                        URL('#'),
                                                        title=SPAN(T('No credits remaining')),
                                                        btn_class='btn-link',
                                                        _class='disabled pull-right grey')

                # Check Credits display
                if subscription.school_subscriptions.Unlimited:
                    credits_display = T('Unlimited')
                else:
                    if credits_remaining < 0:
                        credits_display = SPAN(round(credits_remaining, 1), ' ', T('Credits'))
                    else:
                        credits_display = SPAN(round(credits_remaining, 1), ' ',
                                               T('Credits remaining'))

                # let's put everything together
                option = DIV(DIV(T('Subscription'),
                                 _class='col-md-3 bold'),
                             DIV(subscription.school_subscriptions.Name,
                                 SPAN(XML(' &bull; '),
                                      credits_display,
                                      _class='grey'),
                                 _class='col-md-6'),
                             DIV(button_book,
                                 _class='col-md-3'),
                             _class='col-md-10 col-md-offset-1 col-xs-12')

                options.append(option)
        elif list_type =='shop':
            # show buy link if list type shop
            features = db.customers_shop_features(1)
            if features.Subscriptions:
                button_buy = A(SPAN(T('Shop'), ' ', os_gui.get_fa_icon('fa-chevron-right')),
                               _href=URL('shop', 'subscriptions'),
                               _class='pull-right btn btn-link')

                option = DIV(DIV(T('Subscription'),
                                 _class='col-md-3 bold'),
                             DIV(T('No subscription found'), BR(),
                                 SPAN(T('Click "Shop" to sign up for a subscription'), _class='grey'),
                                 _class='col-md-6'),
                             DIV(button_buy,
                                 _class='col-md-3'),
                             _class='col-md-10 col-md-offset-1 col-xs-12')

                options.append(option)

        # class cards
        classcards = customer.get_classcards(date)
        if classcards:
            for classcard in classcards:
                ccdID = classcard.customers_classcards.id

                ccd = Classcard(ccdID)
                classes_remaining = ccd.get_classes_remaining_formatted()

                if list_type == 'shop':
                    allowed_classes = ccd.get_allowed_classes_booking()
                else:
                    allowed_classes = ccd.get_allowed_classes_attend(public_only=False)

                if not int(clsID) in allowed_classes:
                    # Check book permission
                    button_book = os_gui.get_button('noicon',
                                                    URL('#'),
                                                    title=SPAN(T("Not allowed for this class")),
                                                    btn_class='btn-link',
                                                    _class='disabled pull-right grey')
                else:
                    url = URL(controller, 'class_book', vars={'clsID': clsID,
                                                  'ccdID': ccdID,
                                                  'cuID': customer.row.id,
                                                  'date': date_formatted})
                    button_book = classes_book_options_get_button_book(url)

                option = DIV(DIV(T('Class card'),
                                 _class='col-md-3 bold'),
                             DIV(classcard.school_classcards.Name, ' ',
                                 SPAN(XML(' &bull; '), T('expires'), ' ',
                                      classcard.customers_classcards.Enddate.strftime(DATE_FORMAT),
                                      XML(' &bull; '), classes_remaining,
                                      _class='small_font grey'),
                                 _class='col-md-6'),
                             DIV(button_book,
                                 _class='col-md-3'),
                             _class='col-md-10 col-md-offset-1 col-xs-12')

                options.append(option)
        elif list_type == 'attendance':
                url = URL('customers', 'classcard_add',
                          vars={'cuID': customer.row.id,
                                'clsID': clsID,
                                'date': date_formatted})
                button_add = A(SPAN(T('Sell card'), ' ', os_gui.get_fa_icon('fa-chevron-right')),
                                _href=url,
                                _class='pull-right btn btn-link')


                option = DIV(DIV(T('Class card'),
                                 _class='col-md-3 bold'),
                             DIV(T('No cards found - sell a new card',),
                                 _class='col-md-6'),
                             DIV(button_add,
                                 _class='col-md-3'),
                             _class='col-md-10 col-md-offset-1 col-xs-12')

                options.append(option)

        elif list_type =='shop':
            # show buy link if list type shop
            features = db.customers_shop_features(1)
            if features.Classcards:
                button_buy = A(SPAN(T('Shop'), ' ', os_gui.get_fa_icon('fa-chevron-right')),
                               _href=URL('shop', 'classcards'),
                               _class='pull-right btn btn-link')

                option = DIV(DIV(T('Class card'),
                                 _class='col-md-3 bold'),
                             DIV(T('No class card found'), BR(),
                                 SPAN(T('Click "Shop" to buy a card'), _class='grey'),
                                 _class='col-md-6'),
                             DIV(button_buy,
                                 _class='col-md-3'),
                             _class='col-md-10 col-md-offset-1 col-xs-12')

                options.append(option)

        # Get class prices
        cls = Class(clsID, date)
        prices = cls.get_prices()

        # drop in
        url = URL(controller, 'class_book', vars={'clsID': clsID,
                                      'dropin': 'true',
                                      'cuID': customer.row.id,
                                      'date': date_formatted})
        button_book = classes_book_options_get_button_book(url)

        price = prices['dropin']
        membership_notification = ''
        if customer.has_membership_on_date(date) and prices['dropin_membership']:
            price = prices['dropin_membership']
            membership_notification = SPAN(' ', XML('&bull;'), ' ', '(', T('Membership price'), ')',
                                           _class='grey')

        option = DIV(DIV(T('Drop in'),
                         _class='col-md-3 bold'),
                     DIV(T('Class price:'), ' ', CURRSYM, ' ', format(price, '.2f'), ' ',
                         membership_notification,
                         BR(),
                         SPAN(get_sys_property('shop_classes_dropin_message') or '',
                              _class='grey'),
                         _class='col-md-6'),
                     DIV(button_book,
                         _class='col-md-3'),
                     _class='col-md-10 col-md-offset-1 col-xs-12')

        options.append(option)

        # Trial
        # get trial class price
        if trial:
            url = URL(controller, 'class_book', vars={'clsID': clsID,
                                                      'trial': 'true',
                                                      'cuID': customer.row.id,
                                                      'date': date_formatted})
            button_book = classes_book_options_get_button_book(url)

            price = prices['trial']
            membership_notification = ''
            if customer.has_membership_on_date(date) and prices['trial_membership']:
                price = prices['trial_membership']
                membership_notification = SPAN(' ', XML('&bull;'), ' ', '(', T('Membership price'), ')',
                                               _class='grey')

            option = DIV(DIV(T('Trial'),
                             _class='col-md-3 bold'),
                         DIV(T('Class price:'), ' ', CURRSYM, ' ', format(price, '.2f'), ' ',
                             membership_notification,
                             BR(),
                             SPAN(get_sys_property('shop_classes_trial_message') or '',
                                  _class='grey'),
                             _class='col-md-6'),
                         DIV(button_book,
                             _class='col-md-3'),
                         _class='col-md-10 col-md-offset-1 col-xs-12')

            options.append(option)

        # Complementary
        if complementary:
            options.append(DIV(HR(), _class='col-md-10 col-md-offset-1'))
            url = URL(controller, 'class_book', vars={'clsID': clsID,
                                                      'complementary': 'true',
                                                      'cuID': customer.row.id,
                                                      'date': date_formatted})
            button_book = classes_book_options_get_button_book(url)

            option = DIV(DIV(T('Complementary'),
                             _class='col-md-3 bold'),
                         DIV(T('Give this class for free'),
                             _class='col-md-6'),
                         DIV(button_book,
                             _class='col-md-3'),
                         _class='col-md-10 col-md-offset-1 col-xs-12')

            options.append(option)

        return options


    def _get_teachers_note_modal(self,
                                 cuID,
                                 customers_name,
                                 modals_div):
        '''
            Returns a modal popup for teacher notes
        '''
        T = current.T
        db = current.db
        os_gui = current.globalenv['os_gui']

        notes = LOAD('customers', 'notes.load', ajax=True,
                     vars={'cuID':cuID,
                           'note_type':'teachers'})

        modal_class = 'customers_te_notes_' + unicode(cuID)
        modal_title = SPAN(T('Teacher notes for'), ' ', customers_name)

        query = (db.customers_notes.TeacherNote == True) & \
                (db.customers_notes.auth_customer_id == cuID)
        count_notes = db(query).count()

        notes_text = T('Notes')
        if count_notes == 1:
            notes_text = T('Note ')

        notes_text = SPAN(unicode(count_notes), ' ', notes_text)


        #button_text = XML(SPAN(os_gui.get_fa_icon('fa-sticky-note-o'), ' ', notes_text))
        button_text = XML(notes_text)

        result = os_gui.get_modal(button_text=button_text,
                                  modal_title=modal_title,
                                  modal_content=notes,
                                  modal_class=modal_class,
                                  button_class='btn btn-default btn-checkin')
        modals_div.append(result['modal'])
        button = result['button']

        return dict(modals_div = modals_div,
                    button=button)


    def attendance_sign_in_subscription(self,
                                        cuID,
                                        clsID,
                                        csID,
                                        date,
                                        online_booking=False,
                                        credits_hard_limit=False,
                                        booking_status='booked'):
        '''
            :param cuID: db.auth_user.id
            :param clsID: db.classes.id 
            :param csID: db.customers_subscriptions.id
            :param date: datetime.date
            :return: dict status[ok|fail], message
        '''
        db = current.db
        T = current.T
        DATE_FORMAT = current.DATE_FORMAT
        cache_clear_customers_subscriptions = current.globalenv['cache_clear_customers_subscriptions']


        status = 'fail'
        message = ''
        signed_in = self.attendance_sign_in_check_signed_in(clsID, cuID, date)
        # check credits remaining

        credits_remaining = self._attendance_sign_in_subscription_credits_remaining(csID)
        message_no_credits = T('No credits remaining on this subscription')

        if signed_in:
            message = T("Customer is already checked in")
        elif not credits_remaining and credits_hard_limit:
            # return message, don't sign in
            message = message_no_credits
        else:
            #print 'signing in customer'

            status = 'ok'
            clattID = db.classes_attendance.insert(
                auth_customer_id           = cuID,
                classes_id                 = clsID,
                ClassDate                  = date,
                AttendanceType             = None, # None = subscription
                customers_subscriptions_id = csID,
                online_booking=online_booking,
                BookingStatus=booking_status
                )

            # Take 1 credit
            cls = Class(clsID, date)
            cscID = db.customers_subscriptions_credits.insert(
                customers_subscriptions_id = csID,
                classes_attendance_id = clattID,
                MutationType = 'sub',
                MutationAmount = '1',
                Description = cls.get_name(pretty_date=True)
            )

            #print cscID

            cache_clear_customers_subscriptions(cuID)

            # check subscription classes exceeded
            #result = self._attendance_sign_in_subscription_check_classes_exceeded(csID, clattID, date)
            #if result:
            #    message = result

            # # check credits remaining
            if not credits_remaining:
                message = message_no_credits
            # result = self._attendance_sign_in_subscription_credits_remaining(csID)
            # if result:
            #     message = result

            # check for paused subscription
            result = self._attedance_sign_in_subscription_check_paused(csID, date)
            if result:
                message = result

        return dict(status=status, message=message)


    def _attendance_sign_in_subscription_credits_remaining(self, csID):
        '''
        Check if this subscription has remaining classes, if not, set message

        :param csID:
        :param clattID:
        :param date:
        :return:
        '''
        T = current.T
        db = current.db

        cs = CustomerSubscription(csID)
        balance = cs.get_credits_balance()
        recon_classes = cs.ssu.ReconciliationClasses

        credits_remaining = balance > (recon_classes * -1)

        return credits_remaining


    # def _attendance_sign_in_subscription_check_classes_exceeded(self, csID, clattID, date):
    #     '''
    #         Gets number of weekly classes for a subscription and checks the
    #         attendance table to see if the customer is over the allowed nr of
    #         classes. If so, session.flash is set with a message to notify the user
    #     '''
    #     def insert_exceeded_classes():
    #         db.customers_subscriptions_exceeded.insert(
    #             customers_subscriptions_id = csID,
    #             classes_attendance_id      = clattID,
    #             ClassCount                 = classes_taken
    #         )
    #
    #
    #     T  = current.T
    #     db = current.db
    #     TODAY_LOCAL = current.TODAY_LOCAL
    #
    #     csu = db.customers_subscriptions(csID)
    #     ssu = db.school_subscriptions(csu.school_subscriptions_id)
    #
    #     # Don't do anything if the subscription grants unlimited classes
    #
    #     if ssu.Unlimited:
    #         return
    #
    #     # Ok no unlimited classes, do some checking
    #     if ssu.SubscriptionUnit == 'week':
    #         # check currently used classes
    #         from general_helpers import iso_to_gregorian
    #         iso_week = date.isocalendar()[1]
    #         monday = iso_to_gregorian(date.year, iso_week, 1)
    #         sunday = iso_to_gregorian(date.year, iso_week, 7)
    #
    #         period_start = monday
    #         period_end = sunday
    #     elif ssu.SubscriptionUnit == 'month':
    #         period_start = datetime.date(TODAY_LOCAL.year, TODAY_LOCAL.month, 1)
    #         period_end = get_last_day_month(period_start)
    #
    #     query = (db.classes_attendance.ClassDate >= period_start) & \
    #             (db.classes_attendance.ClassDate <= period_end) & \
    #             (db.classes_attendance.customers_subscriptions_id == csID)
    #
    #     classes_taken = db(query).count()
    #
    #     # check if we should set a message for the user ( None is unlimited )
    #     message = ''
    #     if not ssu.Classes:
    #         message = T("No classes allowed on this subscription")
    #
    #         insert_exceeded_classes()
    #
    #     if ( ssu.Classes and
    #          ssu.SubscriptionUnit == 'week' and
    #          classes_taken > ssu.Classes and
    #          not ssu.Unlimited ):
    #         message = T("Subscription weekly classes exceeded")
    #
    #         insert_exceeded_classes()
    #
    #     # check if we should set a message for the user ( None is unlimited )
    #     if ( ssu.Classes and
    #          ssu.SubscriptionUnit == 'month' and
    #          classes_taken > ssu.Classes and
    #          not ssu.Unlimited ):
    #         message = T("Subscription monthly classes exceeded")
    #
    #         insert_exceeded_classes()
    #
    #     return message


    def _attedance_sign_in_subscription_check_paused(self, csID, date):
        """
            Check if the subscription if paused on given date, if so, display
            a message for the user
        """
        from openstudio.os_customer_subscriptions import CustomerSubscriptions

        T = current.T
        message = ''

        cs = CustomerSubscriptions(csID)
        paused = cs.get_paused(date)
        if paused:
            message = T("Subscription is paused on this date")

        return message


    def _attendance_sign_in_create_invoice(self,
                                           cuID,
                                           caID,
                                           clsID,
                                           date,
                                           product_type):
        """
            Creates an invoice for a drop in or trial class
        """
        db = current.db
        DATE_FORMAT = current.DATE_FORMAT
        T = current.T

        date_formatted = date.strftime(DATE_FORMAT)

        if product_type not in ['trial', 'dropin']:
            raise ValueError('Product type has to be trial or dropin')

        customer = Customer(cuID)
        cls = Class(clsID, date)
        prices = cls.get_prices()

        has_membership = customer.has_membership_on_date(date)

        if product_type == 'dropin':
            price = prices['dropin']

            if has_membership and prices['dropin_membership']:
                price = prices['dropin_membership']

        elif product_type == 'trial':
            price = prices['trial']

            if has_membership and prices['trial_membership']:
                price = prices['trial_membership']

        # check if the price is > 0 when adding an invoice
        if price == 0:
            return

        igpt = db.invoices_groups_product_types(ProductType=product_type)

        iID = db.invoices.insert(
            invoices_groups_id=igpt.invoices_groups_id,
            # classes_attendance_id      = caID,
            Description=T('Class on ') + date_formatted,
            Status='sent'
        )

        # create object to set Invoice# and due date
        invoice = Invoice(iID)
        invoice.item_add_class(
            cuID,
            caID,
            clsID,
            date,
            product_type
        )
        invoice.set_amounts()
        invoice.link_to_customer(cuID)


    def attendance_sign_in_classcard_recurring(self, cuID, clsID, ccdID, date, date_until, online_booking=False, booking_status='booked'):
        """
        :param cuID:
        :param clsID:
        :param ccdID:
        :param date:
        :param until_date:
        :param online_booking:
        :param booking_status:
        :return:
        """
        T = current.T
        TODAY_LOCAL = current.TODAY_LOCAL
        DATE_FORMAT = current.DATE_FORMAT
        get_sys_property = current.globalenv['get_sys_property']

        ccd = Classcard(ccdID)
        ccd_enddate = ccd.classcard.Enddate


        classes_booked = 0
        messages = []

        classes_remaining = ccd.get_classes_remaining()

        shop_classes_advance_booking_limit = get_sys_property('shop_classes_advance_booking_limit')
        # print shop_classes_advance_booking_limit
        book_date_limit = False
        if shop_classes_advance_booking_limit:
            book_date_limit = TODAY_LOCAL + datetime.timedelta(int(shop_classes_advance_booking_limit))


        while date <= date_until:
            # print date
            date_formatted = date.strftime(DATE_FORMAT)
            sign_in_ok = True
            # Check if class is taking place
            cls = Class(clsID, date)
            if cls.is_taking_place() == False:
                sign_in_ok = False
                # print 'class not happening'
                messages.append(T("Class is cancelled or falls within a holiday"))

            # Check online booking spaces available
            if cls.get_full_bookings_shop() == True: # no spaces available
                sign_in_ok = False
                # print "Class full"
                messages.append(T("There are no more spaces for online bookings available for this class"))

            # Check classes remaining
            #if classes_remaining != 'unlimited' or classes_remaining < 1:
            if classes_remaining == 0: # This will pass when it's 'unlimited'
                # print 'no classes remaining'
                date = date_until  # Stop loop
                #TODO: message for customer
                sign_in_ok = False
                messages.append(T('No more classes remaining on this card for class on') + ' ' + date_formatted)

            # Check not past max sign in date
            # print 'booking date limit'
            # print book_date_limit
            if book_date_limit:
                if date > book_date_limit:
                    # print 'class past booking in advance limit'
                    # TODO: message for customer
                    date = date_until # Stop loop
                    sign_in_ok = False

            # Check not past classcard enddate
            if date >= ccd_enddate:
                # print 'class past classcard enddate'
                date = date_until  # Stop loop
                #TODO: message for customer
                sign_in_ok = False
                messages.append(T('Date is past card expiration date:') + ' ' + date_formatted)

            # Check sign in status for fail (if fail, don't add count)
            if sign_in_ok:
                result = self.attendance_sign_in_classcard(cuID, clsID, ccdID, date)
                if not result['status'] == 'fail':
                    messages.append(T("Booked class on") + ' ' + date_formatted)
                    # update remaining classes
                    if not classes_remaining == 'unlimited':
                        classes_remaining -= 1

                    classes_booked += 1

            date += datetime.timedelta(days=7)

        return dict(classes_booked=classes_booked,
                    messages=messages)


    def attendance_sign_in_classcard(self, cuID, clsID, ccdID, date, online_booking=False, booking_status='booked'):
        """
            :param cuID: db.auth_user.id 
            :param clsID: db.classes.id
            :param ccdID: db.customers_classcards.id
            :param date: datetime.date
            :return: 
        """
        db = current.db
        T = current.T

        ccdh = ClasscardsHelper()
        classes_available = ccdh.get_classes_available(ccdID)

        status = 'fail'
        message = ''
        if classes_available:
            signed_in = self.attendance_sign_in_check_signed_in(clsID, cuID, date)
            if signed_in:
                message = T("Already checked in for this class")
            else:
                status = 'success'

                db.classes_attendance.insert(
                    auth_customer_id=cuID,
                    classes_id=clsID,
                    ClassDate=date,
                    AttendanceType=3,  # 3 = classcard
                    customers_classcards_id=ccdID,
                    online_booking=online_booking,
                    BookingStatus=booking_status
                )

                # update class count
                ccdh = ClasscardsHelper()
                ccdh.set_classes_taken(ccdID)
        else:
            message = T("Unable to add, no classes left on card")


        return dict(status=status, message=message)


    def attendance_sign_in_dropin(self,
                                  cuID,
                                  clsID,
                                  date,
                                  online_booking=False,
                                  invoice=True,
                                  booking_status='booked'):
        '''
            :param cuID: db.auth_user.id
            :param clsID: db.classes.id
            :param date: datetime.date
            :return: 
        '''
        db = current.db
        T = current.T

        status = 'fail'
        message = ''
        caID = ''

        signed_in = self.attendance_sign_in_check_signed_in(clsID, cuID, date)
        if signed_in:
            message = T("Already checked in for this class")
        else:
            status = 'ok'
            caID = db.classes_attendance.insert(
                auth_customer_id=cuID,
                classes_id=clsID,
                ClassDate=date,
                AttendanceType=2,  # 2 = drop in class
                online_booking=online_booking,
                BookingStatus=booking_status
            )

            if invoice:
                self._attendance_sign_in_create_invoice(cuID,
                                                        caID,
                                                        clsID,
                                                        date,
                                                        'dropin')

        return dict(status=status, message=message, caID=caID)


    def attendance_sign_in_trialclass(self,
                                      cuID,
                                      clsID,
                                      date,
                                      online_booking=False,
                                      invoice=True,
                                      booking_status='booked'):
        '''
            :param cuID: db.auth_user.id
            :param clsID: db.classes.id
            :param date: datetime.date
            :return: 
        '''
        db = current.db
        T = current.T

        status = 'fail'
        message = ''
        caID = ''

        signed_in = self.attendance_sign_in_check_signed_in(clsID, cuID, date)

        if signed_in:
            message = T("Already checked in for this class")
        else:
            status = 'ok'
            caID = db.classes_attendance.insert(
                auth_customer_id=cuID,
                classes_id=clsID,
                ClassDate=date,
                AttendanceType=1,  # 1 = trial class
                online_booking=online_booking,
                BookingStatus=booking_status
            )

            if invoice:
                self._attendance_sign_in_create_invoice(cuID,
                                                        caID,
                                                        clsID,
                                                        date,
                                                        'trial')

        return dict(status=status, message=message, caID=caID)


    def attendance_sign_in_complementary(self,
                                         cuID,
                                         clsID,
                                         date,
                                         booking_status='booked'):
        '''
            :param cuID: db.auth_user.id
            :param clsID: db.classes.id
            :param date: datetime.date
            :return:
        '''
        db = current.db
        T = current.T

        status = 'fail'
        message = ''
        caID = ''

        signed_in = self.attendance_sign_in_check_signed_in(clsID, cuID, date)

        if signed_in:
            message = T("Already checked in for this class")
        else:
            status = 'ok'
            caID = db.classes_attendance.insert(
                auth_customer_id=cuID,
                classes_id=clsID,
                ClassDate=date,
                AttendanceType=4,  # 4 = Complementary class
                online_booking=False,
                BookingStatus=booking_status
            )


        return dict(status=status, message=message, caID=caID)


    def attendance_sign_in_check_signed_in(self, clsID, cuID, date):
        '''
            Check if a customer isn't already signed in to a class
        '''
        db = current.db
        query = (db.classes_attendance.classes_id == clsID) & \
                (db.classes_attendance.auth_customer_id == cuID) & \
                (db.classes_attendance.ClassDate == date) & \
                (db.classes_attendance.BookingStatus != 'cancelled')

        return db(query).count()


    def attendance_cancel_classes_in_school_holiday(self, shID):
        '''
            :param shID: db.school_holidays.id
            :return: list of db.classes.id
        '''
        db = current.db

        # Get locations
        query = (db.school_holidays_locations.school_holidays_id == shID)
        rows =  db(query).select(db.school_holidays_locations.school_locations_id)
        location_ids = []
        for row in rows:
            location_ids.append(row.school_locations_id)

        # Get classes
        query = (db.classes.school_locations_id.belongs(location_ids))
        rows = db(query).select(db.classes.id)
        class_ids = []
        for row in rows:
            class_ids.append(row.id)

        # Get holiday record and cancel classes
        sh = db.school_holidays(shID)
        self.attendance_cancel_reservations_for_classes(class_ids, sh.Startdate, sh.Enddate)


    def attendance_cancel_reservations_for_classes(self, class_ids, p_start, p_end = None):
        '''
            :param class_ids: list of db.classes.id
            :param p_start: datetime.date
            :param p_end: datetime.date
            :return: None
        '''
        db = current.db

        # in case end period is not specified, assume it's for one day
        if not p_end:
            p_end = p_start

        query = (db.classes_attendance.classes_id.belongs(class_ids)) & \
                (db.classes_attendance.ClassDate >= p_start) & \
                (db.classes_attendance.ClassDate <= p_end)

        db(query).update(BookingStatus='cancelled')

        # Return subscription credits to customers
        csch = CustomersSubscriptionsCredits()
        csch.refund_credits_in_period(query)


class ReservationHelper:
    '''
        This class collects common functions for reservations in OpenStudio
    '''
    def get_reservation(self, cuID, clsID, date):
        '''
           returns reservation for a customer, if any
        '''
        db = current.db
        os_gui = current.globalenv['os_gui']
        DATE_FORMAT = current.DATE_FORMAT
        date_formatted = date.strftime(DATE_FORMAT)

        query = (db.classes_reservation.auth_customer_id == cuID) & \
                (db.classes_reservation.classes_id == clsID) & \
                (db.classes_reservation.Startdate <= date) & \
                ((db.classes_reservation.Enddate >= date) |
                 (db.classes_reservation.Enddate == None))

        rows = db(query).select(db.classes_reservation.ALL)

        if rows:
            return_value = rows
        else:
            return_value = None

        return return_value


class ClassSchedule:
    def __init__(self, date,
                       filter_id_sys_organization = None,
                       filter_id_school_classtype = None,
                       filter_id_school_location = None,
                       filter_id_school_level = None,
                       filter_id_teacher = None,
                       filter_id_status = None,
                       filter_public = False,
                       sorting = 'starttime',
                       trend_medium = None,
                       trend_high = None):

        self.date = date

        self.filter_id_sys_organization = filter_id_sys_organization
        self.filter_id_school_classtype = filter_id_school_classtype
        self.filter_id_school_location = filter_id_school_location
        self.filter_id_teacher = filter_id_teacher
        self.filter_id_school_level = filter_id_school_level
        self.filter_id_status = filter_id_status
        self.filter_public = filter_public
        self.sorting = sorting
        self.trend_medium = trend_medium
        self.trend_high = trend_high

        self.bookings_open = self._get_bookings_open()


    def _get_bookings_open(self):
        '''
            Returns False if no booking limit is defines, otherwise it returns the date from which
            bookings for this class will be accepted.
        '''
        get_sys_property = current.globalenv['get_sys_property']

        bookings_open = False
        shop_classes_advance_booking_limit = get_sys_property('shop_classes_advance_booking_limit')
        if not shop_classes_advance_booking_limit is None:
            delta = datetime.timedelta(days=int(shop_classes_advance_booking_limit))
            bookings_open = self.date - delta

        return bookings_open


    def _get_day_filter_query(self):
        '''
            Returns the filter query for the schedule
        '''
        where = ''

        if self.filter_id_sys_organization:
            where += 'AND cla.sys_organizations_id = ' + unicode(self.filter_id_sys_organization) + ' '
        if self.filter_id_teacher:
            where += 'AND ((CASE WHEN cotc.auth_teacher_id IS NULL \
                            THEN clt.auth_teacher_id  \
                            ELSE cotc.auth_teacher_id END) = '
            where += unicode(self.filter_id_teacher) + ' '
            where += 'OR (CASE WHEN cotc.auth_teacher_id2 IS NULL \
                          THEN clt.auth_teacher_id2  \
                          ELSE cotc.auth_teacher_id2 END) = '
            where += unicode(self.filter_id_teacher) + ') '
        if self.filter_id_school_classtype:
            where += 'AND (CASE WHEN cotc.school_classtypes_id IS NULL \
                           THEN cla.school_classtypes_id  \
                           ELSE cotc.school_classtypes_id END) = '
            where += unicode(self.filter_id_school_classtype) + ' '
        if self.filter_id_school_location:
            where += 'AND (CASE WHEN cotc.school_locations_id IS NULL \
                           THEN cla.school_locations_id  \
                           ELSE cotc.school_locations_id END) = '
            where += unicode(self.filter_id_school_location) + ' '
        if self.filter_id_school_level:
            where += 'AND cla.school_levels_id = '
            where += unicode(self.filter_id_school_level) + ' '
        if self.filter_public:
            where += "AND cla.AllowAPI = 'T' "
            where += "AND sl.AllowAPI = 'T' "
            where += "AND sct.AllowAPI = 'T' "

        return where


    def _get_day_row_status(self, row):
        '''
            Return status for row
        '''
        status = 'normal'
        status_marker = DIV(_class='status_marker bg_green')
        if row.classes_otc.Status == 'cancelled' or row.school_holidays.id:
            status = 'cancelled'
            status_marker = DIV(_class='status_marker bg_orange')
        elif row.classes_otc.Status == 'open':
            status = 'open'
            status_marker = DIV(_class='status_marker bg_red')
        elif row.classes_teachers.teacher_role == 1:
            status = 'subteacher'
            status_marker = DIV(_class='status_marker bg_blue')

        return dict(status=status, marker=status_marker)


    def _get_day_row_teacher_roles(self, row, repr_row):
        '''
            @return: dict with {teacher_role} and {teacher_role2} as keys
             teacher_role and teacher_role2 are names of teacher with labels
              applied
        '''
        os_gui = current.globalenv['os_gui']
        T = current.T

        teacher_id = row.classes_teachers.auth_teacher_id
        teacher_id2 = row.classes_teachers.auth_teacher_id2
        teacher = repr_row.classes_teachers.auth_teacher_id
        teacher2 = repr_row.classes_teachers.auth_teacher_id2
        teacher_role = row.classes_teachers.teacher_role
        teacher_role2 = row.classes_teachers.teacher_role2

        # set label for teacher role
        if teacher_role == 1:  # sub
            teacher_role = SPAN(os_gui.get_os_label('blue', teacher),
                                _title=T('Sub teacher'))
        elif teacher_role == 2:  # assist
            teacher_role = SPAN(os_gui.get_os_label('yellow', teacher),
                                _title=T("Assistant"))
        elif teacher_role == 3:  # karma
            teacher_role = SPAN(os_gui.get_os_label('purple', teacher),
                                _title=T('Karma teacher'))
        else:
            teacher_role = teacher

        # set label for teacher role 2
        if teacher_role2 == 1:  # sub
            teacher_role2 = SPAN(os_gui.get_os_label('blue', teacher2),
                                 _title=T("Sub teacher"))
        elif teacher_role2 == 2:  # assist
            teacher_role2 = SPAN(os_gui.get_os_label('yellow', teacher2),
                                 _title=T("Assistant"))
        elif teacher_role2 == 3:  # karma
            teacher_role2 = SPAN(os_gui.get_os_label('purple', teacher2),
                                 _title=T('Karma teacher'))
        else:
            teacher_role2 = teacher2

        return dict(teacher_role=teacher_role,
                    teacher_role2=teacher_role2)


    def _get_day_get_table_class_trend_data(self):
        '''
            dict containing trend divs for self.date
        '''
        def average(total, classes_counted):
            try:
                average = float(total / classes_counted)
            except ZeroDivisionError:
                average = float(0)

            return average

        DATE_FORMAT = current.DATE_FORMAT
        db = current.db
        T = current.T
        weekday = self.date.isoweekday()

        date_formatted = self.date.strftime(DATE_FORMAT)

        delta = datetime.timedelta(days=28)
        one_month_ago = self.date - delta
        two_months_ago = one_month_ago - delta

        fields = [
            db.classes.id,
            db.classes.Maxstudents,
            db.classes_schedule_count.Attendance4WeeksAgo,
            db.classes_schedule_count.NRClasses4WeeksAgo,
            db.classes_schedule_count.Attendance8WeeksAgo,
            db.classes_schedule_count.NRClasses8WeeksAgo
        ]

        query = '''
            SELECT cla.id,
                   CASE WHEN cotc.Maxstudents IS NOT NULL
                        THEN cotc.Maxstudents
                        ELSE cla.Maxstudents
                        END AS Maxstudents, 
                   clatt_4w_ago.att_4w,
                   clatt_4w_nrclasses.att_4w_nrclasses,
                   clatt_8w_ago.att_8w,
                   clatt_8w_nrclasses.att_8w_nrclasses
            FROM classes cla
            LEFT JOIN
                ( SELECT id,
                         classes_id,
                         ClassDate,
                         Status,
                         Description,
                         school_locations_id,
                         school_classtypes_id,
                         Starttime,
                         Endtime,
                         auth_teacher_id,
                         teacher_role,
                         auth_teacher_id2,
                         teacher_role2,
                         Maxstudents,
                         MaxOnlinebooking
                  FROM classes_otc
                  WHERE ClassDate = '{class_date}' ) cotc
            ON cla.id = cotc.classes_id            
            LEFT JOIN
                    ( SELECT classes_id, COUNT(*) as att_4w
                      FROM classes_attendance
                      WHERE classes_attendance.Classdate <  '{class_date}' AND
                            classes_attendance.Classdate >= '{one_month_ago}'
                      GROUP BY classes_id
                    ) clatt_4w_ago
                    ON clatt_4w_ago.classes_id = cla.id
                LEFT JOIN
                    ( SELECT classes_id, COUNT(DISTINCT ClassDate) as att_4w_nrclasses
                      FROM classes_attendance
                      WHERE classes_attendance.Classdate <  '{class_date}' AND
                            classes_attendance.Classdate >= '{one_month_ago}'
                      GROUP BY classes_id
                    ) clatt_4w_nrclasses
                    ON clatt_4w_nrclasses.classes_id = cla.id
                LEFT JOIN
                    ( SELECT classes_id, COUNT(*) as att_8w
                      FROM classes_attendance
                      WHERE classes_attendance.Classdate <  '{one_month_ago}' AND
                            classes_attendance.Classdate >= '{two_months_ago}'
                      GROUP BY classes_id
                    ) clatt_8w_ago
                    ON clatt_8w_ago.classes_id = cla.id
                LEFT JOIN
                    ( SELECT classes_id, COUNT(DISTINCT ClassDate) as att_8w_nrclasses
                      FROM classes_attendance
                      WHERE classes_attendance.Classdate <  '{one_month_ago}' AND
                            classes_attendance.Classdate >= '{two_months_ago}'
                      GROUP BY classes_id
                    ) clatt_8w_nrclasses
                    ON clatt_8w_nrclasses.classes_id = cla.id
            WHERE cla.Week_day = '{week_day}' AND
                  cla.Startdate <= '{class_date}' AND
                  (cla.Enddate >= '{class_date}' OR cla.Enddate IS NULL)
            '''.format(class_date=self.date,
                       week_day=weekday,
                       one_month_ago=one_month_ago,
                       two_months_ago=two_months_ago)

        rows = db.executesql(query, fields=fields)

        data = {}

        trend_medium = self.trend_medium
        trend_high = self.trend_high

        for row in rows:
            classes_4w = row.classes_schedule_count.NRClasses4WeeksAgo or 0
            attendance_4w = row.classes_schedule_count.Attendance4WeeksAgo or 0
            avg_4w_ago = average(attendance_4w, classes_4w)
            classes_8w = row.classes_schedule_count.NRClasses8WeeksAgo or 0
            attendance_8w = row.classes_schedule_count.Attendance8WeeksAgo or 0
            avg_8w_ago = average(attendance_8w, classes_8w)

            div = DIV()

            display_class = ''
            capacity = ''

            try:
                avg_att_4w_percentage = (avg_4w_ago / row.classes.Maxstudents) * 100
            except ZeroDivisionError:
                avg_att_4w_percentage = 0
            avg_att_4w_percentage_display = round(avg_att_4w_percentage, 2)

            class_trend_text_color = 'grey'
            if trend_medium:
                capacity = ' - ' + T('Capacity filled: ') + unicode(avg_att_4w_percentage_display) + '%'
                if avg_att_4w_percentage < trend_medium:
                    class_trend_text_color = 'text-red'
                else:
                    class_trend_text_color = 'text-yellow'
            if trend_high:
                capacity = ' - ' + T('Capacity filled: ') + unicode(avg_att_4w_percentage_display) + '%'
                if avg_att_4w_percentage >= trend_high:
                    class_trend_text_color = 'text-green'

            avg_4w_ago_display = DIV(SPAN(int(avg_4w_ago), '/', row.classes.Maxstudents),
                                     _title=T("Average attendance past 4 weeks") + ' ' + capacity,
                                     _class='os-trend_avg_4_weeks inline-block ' + class_trend_text_color)
            try:
                if avg_4w_ago >= avg_8w_ago:
                    # calculate percentual increase
                    increase = avg_4w_ago - avg_8w_ago
                    value = int(round(float(increase / avg_8w_ago) * 100))
                    value = unicode(value) + '%'
                    div = DIV(avg_4w_ago_display, ' ',
                              DIV(_class='os-trend_arrow_up'),
                              SPAN(value, _title=T('Increase during past 4 weeks, compared to 8 weeks ago')),
                              ' ',
                              SPAN(_class='icon user icon-user'))
                else:
                    # calculate percentual decrease
                    decrease = avg_8w_ago - avg_4w_ago
                    value = int(round(float(decrease / avg_8w_ago) * 100))
                    value = unicode(value) + '%'
                    div = DIV(avg_4w_ago_display, ' ',
                              DIV(_class='os-trend_arrow_down'),
                              SPAN(value, _title=T('Decrease during past 4 weeks, compared to 8 weeks ago')),
                              ' ',
                              SPAN(_class='icon user icon-user'))

            except ZeroDivisionError:
                div = ''

            data[row.classes.id] = div

        return data


    def _get_day_get_table_class_trend(self):
        '''
            Generates a div that contains the trend for a class.
            Look at past 4 weeks and compare to the classes before it.
            Take cancelled classes & into account by not counting a class
            when it's date doesn't appear in classes_attendance
        '''
        web2pytest = current.globalenv['web2pytest']
        request = current.request
        auth = current.auth
        T = current.T

        # get attendance data from cache or db

        # Don't cache when running tests
        if web2pytest.is_running_under_test(request, request.application):
            data = self._get_day_get_table_class_trend_data()
        else:
            twelve_hours = 12*60*60
            cache = current.cache
            DATE_FORMAT = current.DATE_FORMAT
            # A key that isn't cleared when schedule changes occur.
            cache_key = 'openstudio_classschedule_trend_get_day_table_' + \
                        self.date.strftime(DATE_FORMAT)

            data = cache.ram(cache_key , lambda: self._get_day_get_table_class_trend_data(), time_expire=twelve_hours)

        return data


    def _get_day_get_table_get_permissions(self):
        """
            :return: dict containing button permissions for a user
        """
        auth = current.auth
        permissions = {}

        if auth.has_membership(group_id='Admins') or \
           auth.has_permission('read', 'classes_attendance'):
            permissions['classes_attendance'] = True
        if auth.has_membership(group_id='Admins') or \
           auth.has_permission('read', 'classes_reservation'):
            permissions['classes_reservation'] = True
        if auth.has_membership(group_id='Admins') or \
           auth.has_permission('read', 'classes_waitinglist'):
            permissions['classes_waitinglist'] = True
        if auth.has_membership(group_id='Admins') or \
           auth.has_permission('read', 'classes_notes'):
            permissions['classes_notes'] = True
        if auth.has_membership(group_id='Admins') or \
           auth.has_permission('create', 'classes_otc'):
            permissions['classes_otc'] = True
        if auth.has_membership(group_id='Admins') or \
           auth.has_permission('update', 'classes'):
            permissions['classes'] = True
        if auth.has_membership(group_id='Admins') or \
           auth.has_permission('delete', 'classes'):
            permissions['classes_delete'] = True

        return permissions


    def _get_day_get_table_get_buttons(self, clsID, date_formatted, permissions):
        '''
            Returns buttons for schedule
            - one button group for edit & attendance buttons
            - separate button for delete
        '''
        os_gui = current.globalenv['os_gui']
        T = current.T
        buttons = DIV(_class='pull-right')

        vars = { 'clsID':clsID,
                 'date' :date_formatted }


        links = [['header', T('Class on') + ' ' + date_formatted]]
        # check Attendance permission
        if permissions.get('classes_attendance', False):
            links.append(A(os_gui.get_fa_icon('fa-check-square-o'), T('Attendance'),
                           _href=URL('attendance', vars=vars)))
        # check Reservations permission
        if permissions.get('classes_reservation', False):
            links.append(
                A(os_gui.get_fa_icon('fa-calendar-check-o'),  T('Enrollments'),
                 _href=URL('reservations', vars=vars)))
        # check Waitinglist permission
        if permissions.get('classes_waitinglist', False):
            links.append(
                A(os_gui.get_fa_icon('fa-calendar-o'), T('Waitinglist'),
                  _href=URL('waitinglist', vars=vars)))
        # check Notes permission
        if permissions.get('classes_notes', False):
            links.append(
                A(os_gui.get_fa_icon('fa-sticky-note-o'), T('Notes'),
                  _href=URL('notes', vars=vars)))
        # check permissions to change this class
        if permissions.get('classes_otc', False):
            links.append(A(os_gui.get_fa_icon('fa-pencil'),
                           T('Edit'),
                           _href=URL('class_edit_on_date', vars=vars)))
        # Check permission to update weekly class
        if permissions.get('classes', False):
            links.append('divider')
            links.append(['header', T('All classes in series')])
            links.append(A(os_gui.get_fa_icon('fa-pencil'),
                           T('Edit'), ' ',
                           _href=URL('class_edit', vars=vars)))

        class_menu = os_gui.get_dropdown_menu(
            links=links,
            btn_text=T('Actions'),
            btn_size='btn-sm',
            btn_icon='actions',
            menu_class='btn-group pull-right')

        remove = ''
        if permissions.get('classes_delete'):
            onclick_remove = "return confirm('" + \
                             T('Do you really want to delete this class?') + \
                             "');"
            remove = os_gui.get_button('delete_notext',
                       URL('class_delete', args=[clsID]),
                       onclick=onclick_remove)

            buttons.append(remove)

        return DIV(buttons, class_menu, _class='pull-right schedule_buttons')


    def _get_day_get_table_get_reservations(self, clsID, date_formatted, row, permissions):
        '''
            Returns tools for schedule
            - reservations
        '''
        auth = current.auth
        T = current.T

        tools = DIV()

        # get bookings count
        res = row.classes_schedule_count.Attendance or 0

        filled = SPAN(res, '/', row.classes.Maxstudents)

        link_class = ''
        if res > row.classes.Maxstudents:
            link_class = 'red'

        reservations = A(SPAN(T('Bookings'), ' ', filled),
                         _href=URL('attendance',
                                   vars={'clsID' : clsID,
                                         'date'  : date_formatted}),
                         _class=link_class)

        if permissions.get('classes_attendance', False):
            tools.append(reservations)

        return tools


    def _get_day_table_get_class_messages(self, row, clsID, date_formatted):
        '''
            Returns messages for a class
        '''
        os_gui = current.globalenv['os_gui']
        auth = current.auth
        T = current.T

        class_messages = []

        if row.school_holidays.Description:
            class_messages.append(
                SPAN(SPAN(_class=os_gui.get_icon('education') + ' grey'), ' ',
                     T('Holiday'), ' (',
                     A(row.school_holidays.Description,
                       _href=URL('schedule', 'holiday_edit',
                                 vars={'shID': row.school_holidays.id})),
                     ')'))

        if row.classes_teachers.teacher_role == 1:
            class_messages.append(T('Subteacher'))

        if row.classes_otc.Status == 'cancelled':
            class_messages.append(T('Cancelled'))

        if row.classes_otc.Status == 'open':
            class_messages.append(T('Open'))

        classes_otc_update_permission = auth.has_membership(group_id='Admins') or \
                                        auth.has_permission('update', 'classes_otc')
        if row.classes_otc.id and classes_otc_update_permission:
            _class = os_gui.get_icon('pencil') + ' grey'
            class_messages.append(
                A(SPAN(SPAN(_class=_class), ' ', T('Edited')),
                  _href=URL('class_edit_on_date',
                            vars={'clsID': clsID,
                                  'date': date_formatted})))

            if row.classes_otc.Description:
                class_messages.append(row.classes_otc.Description)

        num_messages = len(class_messages)
        msgs = SPAN()
        append = msgs.append
        for i, msg in enumerate(class_messages):
            append(msg)
            if i + 1 < num_messages:
                append(' | ')

        return msgs


    def _get_day_list_booking_status(self, row):
        """
            :param row: ClassSchedule.get_day_rows() row
            :return: booking status
        """
        pytz = current.globalenv['pytz']
        TIMEZONE = current.TIMEZONE
        NOW_LOCAL = current.NOW_LOCAL
        TODAY_LOCAL = current.TODAY_LOCAL

        local_tz = pytz.timezone(TIMEZONE)

        dt_start = datetime.datetime(self.date.year,
                                     self.date.month,
                                     self.date.day,
                                     int(row.classes.Starttime.hour),
                                     int(row.classes.Starttime.minute))
        dt_start = local_tz.localize(dt_start)
        dt_end = datetime.datetime(self.date.year,
                                   self.date.month,
                                   self.date.day,
                                   int(row.classes.Endtime.hour),
                                   int(row.classes.Endtime.minute))
        dt_end = local_tz.localize(dt_end)

        status = 'finished'
        if row.classes_otc.Status == 'cancelled' or row.school_holidays.id:
            status = 'cancelled'
        elif dt_start <= NOW_LOCAL and dt_end >= NOW_LOCAL:
            # check start time
            status = 'ongoing'
        elif dt_start >= NOW_LOCAL:
            if not self.bookings_open == False and TODAY_LOCAL < self.bookings_open:
                status = 'not_yet_open'
            else:
                # check spaces for online bookings
                spaces = self._get_day_list_booking_spaces(row)
                if spaces < 1:
                    status = 'full'
                else:
                    status = 'ok'

        return status


    def _get_day_list_booking_spaces(self, row):
        """
        :param row: :param row: ClassSchedule.get_day_rows() row
        :return: int - available online booking spaces for a class
        """
        enrollments = row.classes_schedule_count.Reservations or 0
        enrollment_spaces = row.classes.MaxReservationsRecurring or 0
        enrollment_spaces_left = enrollment_spaces - enrollments

        spaces = row.classes.MaxOnlineBooking or 0
        online_booking = row.classes_schedule_count.OnlineBooking or 0
        #attendance = row.classes_schedule_count.Attendance or 0

        available_spaces = (spaces + enrollment_spaces_left) - online_booking
        if available_spaces < 1:
            available_spaces = 0
        #
        # print '### clsID' + unicode(row.classes.id)
        # print spaces
        # print enrollment_spaces_left
        # print online_booking
        # print available_spaces

        return available_spaces


    def _get_day_rows(self):
        """
            Helper function that returns a dict containing a title for the weekday,
            a date for the class and
            a SQLFORM.grid for a selected day which is within 1 - 7 (ISO standard).
        """
        date = self.date
        DATE_FORMAT = current.DATE_FORMAT
        db = current.db
        weekday = date.isoweekday()

        date_formatted = date.strftime(DATE_FORMAT)

        delta = datetime.timedelta(days=28)
        one_month_ago = date - delta
        two_months_ago = one_month_ago - delta

        if self.sorting == 'location':
            orderby_sql = 'location_name, Starttime'
        elif self.sorting == 'starttime':
            orderby_sql = 'Starttime, location_name'

        fields = [
            db.classes.id,
            db.classes_otc.Status,
            db.classes_otc.Description,
            db.classes.school_locations_id,
            db.school_locations.Name,
            db.classes.school_classtypes_id,
            db.classes.school_levels_id,
            db.classes.Week_day,
            db.classes.Starttime,
            db.classes.Endtime,
            db.classes.Startdate,
            db.classes.Enddate,
            db.classes.Maxstudents,
            db.classes.MaxOnlineBooking,
            db.classes.MaxReservationsRecurring,
            db.classes.AllowAPI,
            db.classes.sys_organizations_id,
            db.classes_otc.id,
            db.classes_teachers.id,
            db.classes_teachers.auth_teacher_id,
            db.classes_teachers.teacher_role,
            db.classes_teachers.auth_teacher_id2,
            db.classes_teachers.teacher_role2,
            db.school_holidays.id,
            db.school_holidays.Description,
            db.classes_schedule_count.Attendance,
            db.classes_schedule_count.OnlineBooking,
            db.classes_schedule_count.Reservations
        ]

        where_filter = self._get_day_filter_query()

        query = '''
        SELECT cla.id,
               CASE WHEN cotc.Status IS NOT NULL
                    THEN cotc.Status
                    ELSE 'normal'
                    END AS Status,
               cotc.Description,
               CASE WHEN cotc.school_locations_id IS NOT NULL
                    THEN cotc.school_locations_id
                    ELSE cla.school_locations_id
                    END AS school_locations_id,
               CASE WHEN cotc.school_locations_id IS NOT NULL
                    THEN slcotc.Name
                    ELSE sl.Name
                    END AS location_name,
               CASE WHEN cotc.school_classtypes_id IS NOT NULL
                    THEN cotc.school_classtypes_id
                    ELSE cla.school_classtypes_id
                    END AS school_classtypes_id,
               cla.school_levels_id,
               cla.Week_day,
               CASE WHEN cotc.Starttime IS NOT NULL
                    THEN cotc.Starttime
                    ELSE cla.Starttime
                    END AS Starttime,
               CASE WHEN cotc.Endtime IS NOT NULL
                    THEN cotc.Endtime
                    ELSE cla.Endtime
                    END AS Endtime,
               cla.Startdate,
               cla.Enddate,
               CASE WHEN cotc.Maxstudents IS NOT NULL
                    THEN cotc.Maxstudents
                    ELSE cla.Maxstudents
                    END AS Maxstudents, 
               CASE WHEN cotc.MaxOnlineBooking IS NOT NULL
                    THEN cotc.MaxOnlineBooking
                    ELSE cla.MaxOnlineBooking
                    END AS MaxOnlineBooking,
               cla.MaxReservationsRecurring,             
               cla.AllowAPI,
               cla.sys_organizations_id,
               cotc.id,
               clt.id,
               CASE WHEN cotc.auth_teacher_id IS NOT NULL
                    THEN cotc.auth_teacher_id
                    ELSE clt.auth_teacher_id
                    END AS auth_teacher_id,
               CASE WHEN cotc.auth_teacher_id IS NOT NULL
                    THEN cotc.teacher_role
                    ELSE clt.teacher_role
                    END AS teacher_role,
               CASE WHEN cotc.auth_teacher_id2 IS NOT NULL
                    THEN cotc.auth_teacher_id2
                    ELSE clt.auth_teacher_id2
                    END AS auth_teacher_id2,
               CASE WHEN cotc.auth_teacher_id2 IS NOT NULL
                    THEN cotc.teacher_role2
                    ELSE clt.teacher_role2
                    END AS teacher_role2,
               sho.id,
               sho.Description,
                /* Count attendance for this class */
               ( SELECT count(clatt.id) as count_att
                 FROM classes_attendance clatt
                 WHERE clatt.classes_id = cla.id AND
                       clatt.ClassDAte ='{class_date}' AND
                       clatt.BookingStatus != 'cancelled') AS count_attendance,
               /* Count of online bookings for this class */
               ( SELECT COUNT(clatt.id) as count_atto
                 FROM classes_attendance clatt
                 WHERE clatt.classes_id = cla.id AND
                       clatt.ClassDate = '{class_date}' AND
                       clatt.BookingStatus != 'cancelled' AND
                       clatt.online_booking = 'T'
                 GROUP BY clatt.classes_id ) as count_clatto,
               /* Count of enrollments (reservations) for this class */
               ( SELECT COUNT(clr.id) as count_clr
                 FROM classes_reservation clr
                 WHERE clr.classes_id = cla.id AND
                       (clr.Startdate <= '{class_date}' AND
                        (clr.Enddate >= '{class_date}' OR clr.Enddate IS NULL))
                 GROUP BY clr.classes_id ) as count_clr
        FROM classes cla
        LEFT JOIN
            ( SELECT id,
                     classes_id,
                     ClassDate,
                     Status,
                     Description,
                     school_locations_id,
                     school_classtypes_id,
                     Starttime,
                     Endtime,
                     auth_teacher_id,
                     teacher_role,
                     auth_teacher_id2,
                     teacher_role2,
                     Maxstudents,
                     MaxOnlinebooking
              FROM classes_otc
              WHERE ClassDate = '{class_date}' ) cotc
            ON cla.id = cotc.classes_id
        LEFT JOIN school_locations sl
            ON sl.id = cla.school_locations_id
        LEFT JOIN school_classtypes sct
            ON sct.id = cla.school_classtypes_id
		LEFT JOIN school_locations slcotc
			ON slcotc.id = cotc.school_locations_id
        LEFT JOIN
            ( SELECT id,
                     classes_id,
                     auth_teacher_id,
                     teacher_role,
                     auth_teacher_id2,
                     teacher_role2
              FROM classes_teachers
              WHERE Startdate <= '{class_date}' AND (
                    Enddate >= '{class_date}' OR Enddate IS NULL)
              ) clt
            ON clt.classes_id = cla.id
        LEFT JOIN
            ( SELECT sh.id, sh.Description, shl.school_locations_id
              FROM school_holidays sh
              LEFT JOIN
                school_holidays_locations shl
                ON shl.school_holidays_id = sh.id
              WHERE sh.Startdate <= '{class_date}' AND
                    sh.Enddate >= '{class_date}') sho
            ON sho.school_locations_id = cla.school_locations_id
        WHERE cla.Week_day = '{week_day}' AND
              cla.Startdate <= '{class_date}' AND
              (cla.Enddate >= '{class_date}' OR cla.Enddate IS NULL)
              {where_filter}
        ORDER BY {orderby_sql}
        '''.format(class_date = date,
                   week_day = weekday,
                   orderby_sql = orderby_sql,
                   where_filter = where_filter,
                   one_month_ago = one_month_ago,
                   two_months_ago = two_months_ago)

        rows = db.executesql(query, fields=fields)

        return rows


    def get_day_rows(self):
        """
            Get day rows with caching 
        """
        #web2pytest = current.globalenv['web2pytest']
        #request = current.request

        # # Don't cache when running tests
        # if web2pytest.is_running_under_test(request, request.application):
        #     rows = self._get_day_rows()
        # else:
        #     cache = current.cache
        #     DATE_FORMAT = current.DATE_FORMAT
        #     CACHE_LONG = current.globalenv['CACHE_LONG']
        #     cache_key = 'openstudio_classschedule_get_day_rows_' + self.date.strftime(DATE_FORMAT)
        #     rows = cache.ram(cache_key , lambda: self._get_day_rows(), time_expire=CACHE_LONG)

        rows = self._get_day_rows()

        return rows


    def _get_day_table(self):
        """
            Returns table for today
        """
        os_gui = current.globalenv['os_gui']
        DATE_FORMAT = current.DATE_FORMAT
        ORGANIZATIONS = current.globalenv['ORGANIZATIONS']
        T = current.T
        date_formatted = self.date.strftime(DATE_FORMAT)

        table = TABLE(TR(TH(' ', _class='td_status_marker'), # status marker
                         TH(T('Location'), _class='location'),
                         TH(T('Class type'), _class='classtype'),
                         TH(T('Time'), _class='time'),
                         TH(T('Teacher'), _class='teacher'),
                         TH(T('Level'), _class='level'),
                         TH(T('Public'), _class='api'),
                         TH(T('Trend'), _class='trend'),
                         TH(T('')),
                         _class='os-table_header'),
                      _class='os-schedule')

        rows = self.get_day_rows()

        if len(rows) == 0:
            div_classes=DIV()
        else:
            # Get trend column from cache
            trend_data = self._get_day_get_table_class_trend()
            get_trend_data = trend_data.get

            # avoiding some dots in the loop
            get_status = self._get_day_row_status
            get_teacher_roles = self._get_day_row_teacher_roles
            get_buttons = self._get_day_get_table_get_buttons
            get_reservations = self._get_day_get_table_get_reservations
            get_class_messages = self._get_day_table_get_class_messages

            button_permissions = self._get_day_get_table_get_permissions()

            multiple_organizations = len(ORGANIZATIONS) > 1
            filter_id_status = self.filter_id_status
            msg_no_teacher = SPAN(T('No teacher'), _class='red')

            # Generate list of classes
            for i, row in enumerate(rows):
                repr_row = list(rows[i:i+1].render())[0]
                clsID = row.classes.id

                status_result = get_status(row)
                status = status_result['status']
                status_marker = status_result['marker']

                if filter_id_status and status != filter_id_status:
                    continue

                result = get_teacher_roles(row, repr_row)
                teacher = result['teacher_role']
                teacher2 = result['teacher_role2']

                api = INPUT(value=row.classes.AllowAPI,
                            _type='checkbox',
                            _value='api',
                            _disabled='disabled')

                trend = get_trend_data(row.classes.id, '')
                buttons = get_buttons(clsID, date_formatted, button_permissions)
                reservations = get_reservations(clsID, date_formatted, row, button_permissions)
                class_messages = get_class_messages(row, clsID, date_formatted)

                if multiple_organizations:
                    organization = DIV(repr_row.classes.sys_organizations_id or '',
                                       _class='small_font grey pull-right btn-margin')
                else:
                    organization = ''

                row_class = TR(
                    TD(status_marker),
                    TD(max_string_length(repr_row.classes.school_locations_id, 15)),
                    TD(max_string_length(repr_row.classes.school_classtypes_id, 24)),
                    TD(SPAN(repr_row.classes.Starttime, ' - ', repr_row.classes.Endtime)),
                    TD(teacher if (not status == 'open' and
                                   not row.classes_teachers.auth_teacher_id is None) \
                               else msg_no_teacher),
                    TD(max_string_length(repr_row.classes.school_levels_id, 12)),
                    TD(api),
                    TD(trend),
                    TD(buttons),
                   _class='os-schedule_class')
                row_tools = TR(
                    TD(' '),
                    TD(class_messages, _colspan=3, _class='grey'),
                    TD(teacher2 if not status == 'open' else ''),
                    TD(),
                    TD(),
                    TD(DIV(reservations,
                           _class='os-schedule_links')),
                    TD(organization),
                    _class='os-schedule_links',
                    _id='class_' + unicode(clsID))

                table.append(row_class)
                table.append(row_tools)

        return dict(table=table,
                    weekday=NRtoDay(self.date.isoweekday()),
                    date=date_formatted)


    def get_day_table(self):
        """
            Get day table with caching
        """
        web2pytest = current.globalenv['web2pytest']
        request = current.request
        auth = current.auth

        # Don't cache when running tests
        if web2pytest.is_running_under_test(request, request.application):
            rows = self._get_day_table()
        else:
            cache = current.cache
            DATE_FORMAT = current.DATE_FORMAT
            CACHE_LONG = current.globalenv['CACHE_LONG']
            cache_key = 'openstudio_classschedule_get_day_table_' + \
                        self.date.strftime(DATE_FORMAT) + '_' + \
                        unicode(self.filter_id_school_classtype) + '_' + \
                        unicode(self.filter_id_school_location) + '_' + \
                        unicode(self.filter_id_teacher) + '_' + \
                        unicode(self.filter_id_school_level) + '_' + \
                        unicode(self.filter_id_status) + '_' + \
                        unicode(self.filter_public) + '_' + \
                        self.sorting + '_' + \
                        unicode(self.trend_medium) + '_' + \
                        unicode(self.trend_high)

            rows = cache.ram(cache_key , lambda: self._get_day_table(), time_expire=CACHE_LONG)

        return rows


    def get_day_list(self):
        '''
            Format rows as list
        '''
        os_gui = current.globalenv['os_gui']
        DATE_FORMAT = current.DATE_FORMAT
        T = current.T
        date_formatted = self.date.strftime(DATE_FORMAT)

        rows = self.get_day_rows()

        get_status = self._get_day_row_status

        classes = []
        for i, row in enumerate(rows):
            repr_row = list(rows[i:i+1].render())[0]

            # get status
            status_result = get_status(row)
            status = status_result['status']

            # get teachers
            teacher_id = row.classes_teachers.auth_teacher_id
            teacher_id2 = row.classes_teachers.auth_teacher_id2
            teacher = repr_row.classes_teachers.auth_teacher_id
            teacher2 = repr_row.classes_teachers.auth_teacher_id2
            teacher_role = row.classes_teachers.teacher_role
            teacher_role2 = row.classes_teachers.teacher_role2

            # check filter for teachers
            if self.filter_id_teacher:
                teacher_filter_id = int(self.filter_id_teacher)
                filter_check = (teacher_filter_id == teacher_id or
                                teacher_filter_id == teacher_id2)
                if not filter_check:
                    # break loop if it's not the teacher searched for
                    continue

            # set holidays
            holiday = False
            holiday_description = ''
            if row.school_holidays.id:
                holiday = True
                holiday_description = row.school_holidays.Description

            cancelled = False
            cancelled_description = ''
            if status == 'cancelled':
                cancelled = True
                cancelled_description = row.classes_otc.Description

            subteacher = False
            if ( row.classes_teachers.teacher_role == 1 or
                 row.classes_teachers.teacher_role2 == 1 ):
                subteacher = True

            # shop url
            shop_url = URL('shop', 'classes_book_options', vars={'clsID': row.classes.id,
                                                                 'date' : date_formatted},
                           scheme=True,
                           host=True,
                           extension='')

            # populate class data
            data = dict()
            data['ClassesID'] = row.classes.id
            data['LocationID'] = row.classes.school_locations_id
            data['Location'] = repr_row.classes.school_locations_id
            data['Starttime'] = repr_row.classes.Starttime
            data['time_starttime'] = row.classes.Starttime
            data['Endtime'] = repr_row.classes.Endtime
            data['time_endtime'] = row.classes.Endtime
            data['ClassTypeID'] = row.classes.school_classtypes_id
            data['ClassType'] = repr_row.classes.school_classtypes_id
            data['TeacherID'] = teacher_id
            data['TeacherID2'] = teacher_id2
            data['Teacher'] = teacher
            data['Teacher2'] = teacher2
            data['LevelID'] = row.classes.school_levels_id
            data['Level'] = repr_row.classes.school_levels_id
            data['Subteacher'] = subteacher
            data['Cancelled'] = cancelled
            data['CancelledDescription'] = cancelled_description
            data['Holiday'] = holiday
            data['HolidayDescription'] = holiday_description
            data['MaxStudents'] = row.classes.Maxstudents or 0 # Spaces for a class
            data['CountAttendance'] = row.classes_schedule_count.Attendance or 0
            data['CountAttendanceOnlineBooking'] = row.classes_schedule_count.OnlineBooking or 0
            data['BookingSpacesAvailable'] = self._get_day_list_booking_spaces(row)
            data['BookingStatus'] = self._get_day_list_booking_status(row)
            data['BookingOpen'] = self.bookings_open
            data['LinkShop'] = shop_url

            classes.append(data)

        return classes


class Classcard:
    '''
        Customer classcard
    '''

    def __init__(self, ccdID):
        '''
            Set some initial values
        '''
        db = current.db

        self.ccdID = ccdID
        self.classcard = db.customers_classcards(ccdID)
        self.scdID = self.classcard.school_classcards_id
        self.school_classcard = db.school_classcards(self.scdID)

        self.price = self.school_classcard.Price
        self.name = self.school_classcard.Name
        self.classes = self.school_classcard.Classes
        self.unlimited = self.school_classcard.Unlimited
        self.cuID = self.classcard.auth_customer_id

    def get_name(self):
        '''
            Returns name of classcard
        '''
        return self.school_classcard.Name

    def get_auth_customer_id(self):
        '''
            Returns auth_customer_id
        '''
        return self.classcard.auth_customer_id

    def get_tax_rate_percentage(self):
        '''
            Returns the tax rate percentage for a card
            Returns None if nothing is set
        '''
        db = current.db

        trID = self.school_classcard.tax_rates_id
        if not trID:
            return None

        tax_rate = db.tax_rates(trID)

        return tax_rate.Percentage


    def get_rows_classes_taken(self):
        '''
            Returns rows of classes taken on this card
        '''
        db = current.db

        fields = [
            db.classes_attendance.id,
            db.classes_attendance.ClassDate,
            db.classes.id,
            db.classes.school_locations_id,
            db.classes.school_classtypes_id,
            db.classes.Starttime
        ]

        orderby_sql = 'clatt.ClassDate'

        query = '''
        SELECT clatt.id,
               clatt.ClassDate,
               cla.id,
               CASE WHEN cotc.school_locations_id IS NOT NULL
                    THEN cotc.school_locations_id
                    ELSE cla.school_locations_id
               END AS school_locations_id,
               CASE WHEN cotc.school_classtypes_id IS NOT NULL
                    THEN cotc.school_classtypes_id
                    ELSE cla.school_classtypes_id
               END AS school_classtypes_id,
               CASE WHEN cotc.Starttime IS NOT NULL
                    THEN cotc.Starttime
                    ELSE cla.Starttime
               END AS Starttime
        FROM classes_attendance clatt
        LEFT JOIN classes cla on cla.id = clatt.classes_id
        LEFT JOIN
            ( SELECT id,
                     classes_id,
                     ClassDate,
                     Status,
                     school_locations_id,
                     school_classtypes_id,
                     Starttime,
                     Endtime,
                     auth_teacher_id,
                     teacher_role,
                     auth_teacher_id2,
                     teacher_role2
              FROM classes_otc ) cotc
            ON clatt.classes_id = cotc.classes_id AND clatt.ClassDate = cotc.ClassDate
        WHERE clatt.customers_classcards_id = {ccdID}
        ORDER BY {orderby_sql}
        '''.format(orderby_sql=orderby_sql,
                   ccdID=self.ccdID)

        rows = db.executesql(query, fields=fields)

        return rows


    def get_classes_remaining(self):
        '''
            :return: Remaining classes
        '''
        db = current.db

        if self.unlimited:
            return 'unlimited'

        query = (db.classes_attendance.customers_classcards_id == self.ccdID) & \
                (db.classes_attendance.BookingStatus != 'cancelled')
        used = db(query).count()
        return self.classes - used


    def get_classes_remaining_formatted(self):
        '''
            :return: Representation of remaining classes
        '''
        db = current.db
        T = current.T

        remaining = self.get_classes_remaining()

        if remaining == 'unlimited':
            remaining = T('Unlimited')

        text = T("Classes")
        if remaining == 1:
           text = T("Class")

        return SPAN(unicode(remaining), ' ', text, ' ', T("remaining"))


    def _get_allowed_classes_format(self, class_ids):
        '''
            :param class_ids: list of db.classes.id
            :return: html table
        '''
        T = current.T
        db = current.db
        TODAY_LOCAL = current.TODAY_LOCAL

        query = (db.classes.AllowAPI == True) & \
                (db.classes.id.belongs(class_ids)) & \
                (db.classes.Startdate <= TODAY_LOCAL) & \
                ((db.classes.Enddate == None) |
                 (db.classes.Enddate >= TODAY_LOCAL))
        rows = db(query).select(db.classes.ALL,
                                orderby=db.classes.Week_day|db.classes.Starttime|db.classes.school_locations_id)

        header = THEAD(TR(TH(T('Day')),
                          TH(T('Time')),
                          TH(T('Location')),
                          TH(T('Class'))))
        table = TABLE(header, _class='table table-striped table-hover')
        for i, row in enumerate(rows):
            repr_row = list(rows[i:i + 1].render())[0]

            tr = TR(TD(repr_row.Week_day),
                    TD(repr_row.Starttime, ' - ', repr_row.Endtime),
                    TD(repr_row.school_locations_id),
                    TD(repr_row.school_classtypes_id))

            table.append(tr)

        return table


    # def get_allowed_classes_enrollment(self, public_only=True, formatted=False):
    #     '''
    #         :return: return: list of db.classes.db that are allowed to be enrolled in using this subscription
    #     '''
    #     permissions = self.get_class_permissions(public_only=public_only)
    #     class_ids = []
    #     for clsID in permissions:
    #         try:
    #             if permissions[clsID]['Enroll']:
    #                 class_ids.append(clsID)
    #         except KeyError:
    #             pass
    #
    #     if not formatted:
    #         return class_ids
    #     else:
    #         return self._get_allowed_classes_format(class_ids)


    def get_allowed_classes_booking(self, public_only=True, formatted=False):
        """
            :return: return: list of db.classes.db that are allowed to be booked using this subscription
        """
        permissions = self.get_class_permissions(public_only=public_only)
        class_ids = []
        for clsID in permissions:
            try:
                if permissions[clsID]['ShopBook']:
                    class_ids.append(clsID)
            except KeyError:
                pass


        if not formatted:
            return class_ids
        else:
            return self._get_allowed_classes_format(class_ids)


    def get_allowed_classes_attend(self, public_only=True, formatted=False):
        """
            :return: return list of db.classes that are allowed to be attended using this subscription
        """
        permissions = self.get_class_permissions(public_only=public_only)
        class_ids = []
        for clsID in permissions:
            try:
                if permissions[clsID]['Attend']:
                    class_ids.append(clsID)
            except KeyError:
                pass


        if not formatted:
            return class_ids
        else:
            return self._get_allowed_classes_format(class_ids)


    def _get_class_permissions_format(self, permissions):
        '''
            :param permissions: dictionary of class permissions
            :return: html table
        '''
        T = current.T
        db = current.db
        os_gui = current.globalenv['os_gui']
        TODAY_LOCAL = current.TODAY_LOCAL

        class_ids = []
        for clsID in permissions:
            class_ids.append(clsID)

        query = (db.classes.AllowAPI == True) & \
                (db.classes.id.belongs(class_ids)) & \
                (db.classes.Startdate <= TODAY_LOCAL) & \
                ((db.classes.Enddate == None) |
                 (db.classes.Enddate >= TODAY_LOCAL))
        rows = db(query).select(db.classes.ALL,
                                orderby=db.classes.Week_day|db.classes.Starttime|db.classes.school_locations_id)

        header = THEAD(TR(TH(T('Day')),
                          TH(T('Time')),
                          TH(T('Location')),
                          TH(T('Class')),
                          #TH(T('Enroll')),
                          TH(T('Book in advance')),
                          TH(T('Attend'))))

        table = TABLE(header, _class='table table-striped table-hover')
        green_check = SPAN(os_gui.get_fa_icon('fa-check'), _class='text-green')

        for i, row in enumerate(rows):
            repr_row = list(rows[i:i + 1].render())[0]

            class_permission = permissions[row.id]
            enroll = class_permission.get('Enroll', '')
            shopbook = class_permission.get('ShopBook', '')
            attend = class_permission.get('Attend', '')

            if enroll:
                enroll = green_check

            if shopbook:
                shopbook = green_check

            if attend:
                attend = green_check

            tr = TR(TD(repr_row.Week_day),
                    TD(repr_row.Starttime, ' - ', repr_row.Endtime),
                    TD(repr_row.school_locations_id),
                    TD(repr_row.school_classtypes_id),
                    #TD(enroll),
                    TD(shopbook),
                    TD(attend))

            table.append(tr)

        return table


    def get_class_permissions(self, public_only=True, formatted=False):
        '''
            :return: return list of class permissons (clsID: enroll, book in shop, attend)
        '''
        db = current.db

        # get groups for classcard
        query = (db.school_classcards_groups_classcards.school_classcards_id == self.scdID)
        rows = db(query).select(db.school_classcards_groups_classcards.school_classcards_groups_id)

        group_ids = []
        for row in rows:
            group_ids.append(row.school_classcards_groups_id)


        # get permissions for classcard group
        left = [db.classes.on(db.classes_school_classcards_groups.classes_id == db.classes.id)]
        query = (db.classes_school_classcards_groups.school_classcards_groups_id.belongs(group_ids))

        if public_only:
            query &= (db.classes.AllowAPI == True)

        rows = db(query).select(db.classes_school_classcards_groups.ALL,
                                left=left)

        permissions = {}
        for row in rows:
            clsID = row.classes_id
            if clsID not in permissions:
                permissions[clsID] = {}

            if row.Enroll:
                permissions[clsID]['Enroll'] = True
            if row.ShopBook:
                permissions[clsID]['ShopBook'] = True
            if row.Attend:
                permissions[clsID]['Attend'] = True

        if not formatted:
            return permissions
        else:
            return self._get_class_permissions_format(permissions)


class ClasscardsHelper:
    '''
        Class that contains functions for classcards
    '''

    def set_classes_taken(self, ccdID):
        '''
            Returns payment for a cuID and wspID
        '''
        db = current.db

        query = (db.classes_attendance.customers_classcards_id == ccdID) & \
                (db.classes_attendance.BookingStatus != 'cancelled')
        count = db(query).count()

        classcard = db.customers_classcards(ccdID)
        classcard.ClassesTaken = count
        classcard.update_record()

    def get_classes_taken(self, ccdID):
        '''
            Returns classes taken on a card
        '''
        db = current.db

        query = (db.classes_attendance.customers_classcards_id == ccdID) & \
                (db.classes_attendance.BookingStatus != 'cancelled')
        count = db(query).count()

        return count

    def get_classes_total(self, ccdID):
        '''
            Returns the total classes on a card
        '''
        db = current.db
        classcard = db.customers_classcards(ccdID)
        school_classcard = db.school_classcards(classcard.school_classcards_id)

        if school_classcard.Unlimited:
            return current.T('Unlimited')
        else:
            return school_classcard.Classes

    def get_classes_remaining(self, ccdID):
        '''
            Returns number of classes remaining on a card
        '''
        taken = self.get_classes_taken(ccdID)
        total = self.get_classes_total(ccdID)

        if total == current.T('Unlimited'):
            return total
        else:
            return total - taken

    def get_classes_available(self, ccdID):
        '''
            Returns True if classes are available on a card
            and False if not.
        '''
        remaining = self.get_classes_remaining(ccdID)

        if remaining > 0:
            available = True
        else:
            available = False

        return available

    def represent_validity(self, validity_months=None, validity_days=None):
        '''
            Represent validity for a school_classcard
        '''
        validity = SPAN()

        if validity_months:
            months = SPAN(validity_months, T(" Month"))
            if validity_months > 1:
                months.append(T('s'))
            validity.append(months)
            validity.append(' ')

        if validity_months and validity_days:
            validity.append(T(" and "))

        if validity_days:
            days = SPAN(validity_days, T(" Day"))
            if validity_days > 1:
                days.append(T('s'))
            validity.append(days)

        return validity


class Workshop:
    def __init__(self, wsID):
        self.wsID = wsID

        db = current.db
        query = (db.workshops.id == self.wsID)
        rows = db(query).select(db.workshops.ALL)
        self.workshop = rows.first()
        repr_row = rows.render(0)

        self.Name = self.workshop.Name
        self.Tagline = self.workshop.Tagline or ''
        self.Startdate = self.workshop.Startdate
        self.Startdate_formatted = repr_row.Startdate
        self.Enddate = self.workshop.Enddate
        self.Enddate_formatted = repr_row.Enddate
        self.Starttime = self.workshop.Starttime
        self.Endtime = self.workshop.Endtime
        self.auth_teacher_id = self.workshop.auth_teacher_id
        self.auth_teacher_id2 = self.workshop.auth_teacher_id2
        self.auth_teacher_name = repr_row.auth_teacher_id
        self.auth_teacher_name2 = repr_row.auth_teacher_id2
        self.Preview = self.workshop.Preview
        self.Description = self.workshop.Description
        self.school_levels_id = self.workshop.school_levels_id
        self.school_level = repr_row.school_levels_id
        self.school_locations_id = self.workshop.school_locations_id
        self.school_location = repr_row.school_locations_id
        self.picture = self.workshop.picture
        self.thumbsmall = self.workshop.thumbsmall
        self.thumblarge = self.workshop.thumblarge
        self.picture_2 = self.workshop.picture_2
        self.thumbsmall_2 = self.workshop.thumbsmall_2
        self.thumblarge_2 = self.workshop.thumblarge_2
        self.picture_3 = self.workshop.picture_3
        self.thumbsmall_3 = self.workshop.thumbsmall_3
        self.thumblarge_3 = self.workshop.thumblarge_3
        self.picture_4 = self.workshop.picture_3
        self.thumbsmall_4 = self.workshop.thumbsmall_4
        self.thumblarge_4 = self.workshop.thumblarge_4
        self.picture_5 = self.workshop.picture_5
        self.thumbsmall_5 = self.workshop.thumbsmall_5
        self.thumblarge_5 = self.workshop.thumblarge_5
        self.PublicWorkshop = self.workshop.PublicWorkshop


    def get_products(self, filter_public = False):
        '''
            :param filter_public: boolean - show only Public products when set to True
            :return: workshop product rows for a workshop
        '''
        db = current.db

        query = (db.workshops_products.workshops_id == self.wsID)
        if filter_public:
            query &= (db.workshops_products.PublicProduct == True)

        rows = db(query).select(db.workshops_products.ALL,
                                orderby = ~db.workshops_products.FullWorkshop)

        return rows


    def get_full_workshop_price(self):
        '''
            :return: price of full workshop product
        '''
        full_ws_product = self.get_products().first()

        return full_ws_product.Price


    def get_activities(self):
        db = current.db

        query = (db.workshops_activities.workshops_id == self.wsID)
        rows = db(query).select(db.workshops_activities.ALL,
                                orderby = db.workshops_activities.Activitydate|\
                                          db.workshops_activities.Starttime)

        return rows


    def update_dates_times(self):
        '''
            After adding/editing/deleting a workshop activity, call this function
            to update the dates & times on the db.workshops record
        '''
        activities = self.get_activities()

        time_from  = None
        time_until = None
        date_from  = None
        date_until = None
        if len(activities) > 0:
            date_from = activities[0].Activitydate
            date_until = activities[0].Activitydate
            time_from = activities[0].Starttime
            time_until = activities[0].Endtime

        if len(activities) > 1:
            date_until = activities[len(activities) - 1].Activitydate
            time_until = activities[len(activities) - 1].Endtime

        self.workshop.Startdate = date_from
        self.workshop.Enddate   = date_until
        self.workshop.Starttime = time_from
        self.workshop.Endtime   = time_until
        self.workshop.update_record()


    def cancel_orders_with_sold_out_products(self):
        '''
            After selling a product online or adding a customer to a product, check whether products aren't sold out.
            If a product is sold out, check for open orders containing the sold out product and cancel them.
        '''
        db = current.db

        products = self.get_products()
        for product in products:
            wsp = WorkshopProduct(product.id)
            if wsp.is_sold_out():
                # Cancel all unpaid orders with this product
                left = [db.customers_orders.on(
                    db.customers_orders_items.customers_orders_id == db.customers_orders.id)]
                query = ((db.customers_orders.Status == 'awaiting_payment') |
                         (db.customers_orders.Status == 'received')) & \
                        (db.customers_orders_items.workshops_products_id == product.id)
                sold_out_rows = db(query).select(db.customers_orders_items.ALL,
                                                 db.customers_orders.ALL,
                                                 left=left)
                for sold_out_row in sold_out_rows:
                    order = Order(sold_out_row.customers_orders.id)
                    order.set_status_cancelled()


class WorkshopsHelper:
    def get_customer_info(self, wsp_cuID, wsID, WorkshopInfo, resend_link=''):
        '''
            Returns checkboxes for payment confirmation and workshop info
            wsp_cuID = workshops_products_customers.id
        '''
        T = current.T

        form = SQLFORM.factory(
            Field('WorkshopInfo', 'boolean',
                  default=WorkshopInfo)
        )

        hidden_field_id = INPUT(_type="hidden",
                                _name="id",
                                _value=wsp_cuID)

        inputs = DIV(
            form.custom.widget.WorkshopInfo, ' ',
            LABEL(T('Event Info'),
                  _for='no_table_WorkshopInfo')
        )

        form = DIV(form.custom.begin,
                   #table,
                   inputs,
                   hidden_field_id,
                   form.custom.end,
                   resend_link)

        return form


    def get_all_workshop_customers(self, wsID, count=False, ids_only=False):
        '''
            Returns a list of gluon.dal.row objects for each customer attending
            a workshop

            If count is set to True, return a count of customers attending
            the workshop
        '''
        # Get list of all customers with email for a workshop
        # Get all workshop_products_ids
        db = current.db
        query = (db.workshops_products.workshops_id == wsID)
        rows = db(query).select(db.workshops_products.id)
        products_ids = []
        for row in rows:
            products_ids.append(row.id)

        wspID = db.workshops_products_customers.workshops_products_id

        query = (wspID.belongs(products_ids))
        customers_rows = []
        left = [db.auth_user.on(db.auth_user.id == \
                                db.workshops_products_customers.auth_customer_id)]
        rows = db(query).select(db.workshops_products_customers.ALL,
                                db.auth_user.id,
                                db.auth_user.trashed,
                                db.auth_user.thumbsmall,
                                db.auth_user.first_name,
                                db.auth_user.last_name,
                                left=left )

        for row in rows:
            if row not in customers_rows:
                customers_rows.append(row)

        if count:
            return_value = len(customers_rows)
        elif ids_only:
            return_value = [row.auth_user.id for row in rows]
        else:
            return_value = customers_rows

        return return_value


    def get_product_sell_buttons(self, cuID, wsID, wspID, cid):
        """
            Returns buttons for workshop_product_sell list type
            This is a select button to select a customer to sell a product to
        """
        db = current.db
        os_gui = current.globalenv['os_gui']

        buttons = DIV(DIV(current.T("Already added"), _class='btn'),
                     _class='btn-group pull-right hidden')

        products_sold = db.workshops_products_customers
        # find full workshop id
        fwspID = self.get_full_workshop_product_id_for_workshop(wsID)

        # check if full workshop has been sold
        check_full_ws = products_sold(workshops_products_id=fwspID,
                                      auth_customer_id=cuID)

        # check if product has been sold
        check = products_sold(workshops_products_id=wspID,
                              auth_customer_id=cuID)

        if not check and not check_full_ws:
            buttons = DIV(os_gui.get_button('add',
                                        URL('events',
                                            'ticket_sell_to_customer',
                                            vars={'cuID' : cuID,
                                                  'wsID' : wsID,
                                                  'wspID': wspID},
                                            extension='')),
                         A(current.T('To waitinglist'),
                           _href=URL('events',
                                     'ticket_sell_to_customer',
                                     vars={'cuID'     : cuID,
                                           'wsID'     : wsID,
                                           'wspID'    : wspID,
                                           'waiting'  : True},
                                     extension=''),
                           _class='btn btn-default btn-sm'),
                        _class='btn-group pull-right')

        return buttons

    def get_full_workshop_product_id_for_workshop(self, wsID):
        '''
            Return id of full workshop product
        '''
        db = current.db
        query = (db.workshops_products.workshops_id == wsID) & \
                (db.workshops_products.FullWorkshop == True)

        return db(query).select().first().id


class WorkshopProduct:
    '''
        Class for workshop products
    '''
    def __init__(self, wspID):
        db = current.db

        self.wspID = int(wspID)
        self.workshop_product = db.workshops_products(self.wspID)
        self.workshop         = db.workshops(self.workshop_product.workshops_id)

        self.name          = self.workshop_product.Name
        self.workshop_name = self.workshop.Name
        self.wsID          = self.workshop.id
        self.tax_rates_id  = self.workshop_product.tax_rates_id

        self._set_price()


    def _set_price(self):
        if self.workshop_product.Price:
            self.price = self.workshop_product.Price
        else:
            self.price = 0


    def get_price(self):
        return self.workshop_product.Price


    def get_tax_rate_percentage(self):
        '''
            Returns the tax percentage for a workshop product, if any
        '''
        db = current.db

        if self.workshop_product.tax_rates_id:
            tax_rate = db.tax_rates(self.workshop_product.tax_rates_id)
            tax_rate_percentage = tax_rate.Percentage
        else:
            tax_rate_percentage = None

        return tax_rate_percentage


    def get_activities(self):
        '''
            Returns all activities for a workshop product
        '''
        db = current.db

        if self.workshop_product.FullWorkshop:
            query = (db.workshops_activities.workshops_id == self.workshop.id)
            left = None
        else:
            query = (db.workshops_products_activities.workshops_products_id == self.wspID)
            left = [ db.workshops_activities.on(
                db.workshops_products_activities.workshops_activities_id ==
                db.workshops_activities.id) ]


        rows = db(query).select(db.workshops_activities.ALL,
                                left=left,
                                orderby=db.workshops_activities.Activitydate|\
                                        db.workshops_activities.Starttime)

        return rows


    def is_sold_to_customer(self, cuID):
        '''
            :param cuID: db.auth_user.id
            :return: True when sold to customer, False when not
        '''
        db = current.db

        query = (db.workshops_products_customers.auth_customer_id == cuID) & \
                (db.workshops_products_customers.workshops_products_id == self.wspID)
        count = db(query).count()

        if count > 0:
            return True
        else:
            return False


    def is_sold_out(self):
        '''
            This function checks if a product is sold out
            It's sold out when any of the activities it contains is completely full
        '''
        def activity_list_customers_get_list_activity_query(wsaID):
            '''
                Returns a query that returns a set of all customers in a specific
                workshop activity, without the full workshop customers
            '''
            query = (db.workshops_activities.id ==
                     db.workshops_products_activities.workshops_activities_id) & \
                    (db.workshops_products_customers.workshops_products_id ==
                     db.workshops_products_activities.workshops_products_id) & \
                    (db.workshops_products_activities.workshops_activities_id ==
                     wsaID) & \
                    (db.workshops_products_customers.Waitinglist == False)

            return query

        def activity_count_reserved(wsaID):
            # count full workshop customers
            query = (db.workshops_products_customers.workshops_products_id == fwsID)
            count_full_ws = db(query).count()
            # count activity customers
            query = activity_list_customers_get_list_activity_query(wsaID)
            count_activity = db(query).count()

            return count_full_ws + count_activity

        db = current.db
        check = False

        fwsID = workshops_get_full_workshop_product_id(self.workshop.id)


        if self.wspID == fwsID:
            # Full workshops check, check if any activity is full
            query = (db.workshops_activities.workshops_id == self.workshop.id)
            rows = db(query).select(db.workshops_activities.ALL)
            for row in rows:
                reserved = activity_count_reserved(row.id)
                if reserved >= row.Spaces:
                    check = True
                    break
        else:
            # Product check, check if any a activity is full
            left = [ db.workshops_activities.on(
                db.workshops_products_activities.workshops_activities_id ==
                db.workshops_activities.id
            )]
            query = (db.workshops_products_activities.workshops_products_id == self.wspID)
            rows = db(query).select(db.workshops_products_activities.ALL,
                                    db.workshops_activities.Spaces,
                                    left=left)
            for row in rows:
                wsaID = row.workshops_products_activities.workshops_activities_id
                reserved = activity_count_reserved(wsaID)
                if reserved >= row.workshops_activities.Spaces:
                    check = True
                    break

        return check


    def add_to_shoppingcart(self, cuID):
        '''
            Add a workshop product to the shopping cart of a customer
        '''
        db = current.db

        db.customers_shoppingcart.insert(
            auth_customer_id = cuID,
            workshops_products_id = self.wspID
        )


    def sell_to_customer(self, cuID, waitinglist=False, invoice=True):
        '''
            Sells a workshop to a customer and creates an invoice
            Creates an invoice when a workshop product is sold
        '''
        db = current.db
        T = current.T

        info = False
        if self.workshop.AutoSendInfoMail:
            info = True

        wspID = self.wspID
        wspcID = db.workshops_products_customers.insert(
            auth_customer_id=cuID,
            workshops_products_id=wspID,
            Waitinglist=waitinglist,
            WorkshopInfo=info)

        ##
        # Add invoice
        ##
        if invoice and not waitinglist and self.price > 0:
            igpt = db.invoices_groups_product_types(ProductType = 'wsp')

            description = self.workshop_name + ' - ' + self.name
            
            iID = db.invoices.insert(
                invoices_groups_id = igpt.invoices_groups_id,
                Description = description,
                Status = 'sent'
                )

            # link invoice to sold workshop product for customer
            db.invoices_workshops_products_customers.insert(
                invoices_id = iID,
                workshops_products_customers_id = wspcID )

            # create object to set Invoice# and due date
            invoice = Invoice(iID)
            next_sort_nr = invoice.get_item_next_sort_nr()

            price = self.price

            iiID = db.invoices_items.insert(
                invoices_id  = iID,
                ProductName  = T("Event"),
                Description  = description,
                Quantity     = 1,
                Price        = price,
                Sorting      = next_sort_nr,
                tax_rates_id = self.tax_rates_id,
            )

            invoice.set_amounts()
            invoice.link_to_customer(cuID)

        ##
        # Send info mail to customer if we have some practical info
        ##
        if self.workshop.AutoSendInfoMail:
            osmail = OsMail()
            msgID = osmail.render_email_template('workshops_info_mail', workshops_products_customers_id=wspcID)
            osmail.send(msgID, cuID)

        if not waitinglist:
            # Check if sold out
            if self.is_sold_out():
                # Cancel all unpaid orders with a sold out product for this workshop
                ws = Workshop(self.wsID)
                ws.cancel_orders_with_sold_out_products()

        return wspcID


class WorkshopSchedule:
    def __init__(self, filter_date_start,
                       filter_date_end = None,
                       filter_archived = True,
                       filter_only_public = True,
                       sorting = 'date'):

        self.filter_date_start = filter_date_start
        self.filter_date_end = filter_date_end
        self.filter_archived = filter_archived
        self.filter_only_public = filter_only_public

        self.sorting = sorting

    def _get_workshops_rows_filter_query(self):
        '''
            Apply filters to workshops
        '''
        where = ''
        if self.filter_archived:
            where += "AND ws.Archived='F'"
            where += ' '

        if self.filter_only_public:
            where += "AND ws.PublicWorkshop='T'"
            where += ' '

        #TODO: check first activity date as startdate ... or create function in workshops.py that updates dates
        # & times for workshops when an activity is added/updated/deleted.
        if self.filter_date_start:
            where += "AND ws.Startdate >= '" + unicode(self.filter_date_start) + "'"
            where += ' '

        if self.filter_date_end:
            where += "AND ws.Enddate <= " + unicode(self.filter_date_end) + "'"
            where += ' '

        return where


    def _get_workshops_rows_orderby(self):
        '''
            Apply right sorting to rows
        '''
        db = current.db
        orderby = 'ws.Startdate'

        if self.sorting == 'name':
            orderby = 'ws.Name'

        return orderby


    def get_workshops_rows(self):
        '''
            Gets workshop rows
        '''
        db = current.db

        orderby_sql = self._get_workshops_rows_orderby()
        where_filter = self._get_workshops_rows_filter_query()

        fields = [
            db.workshops.id,
            db.workshops.Name,
            db.workshops.Tagline,
            db.workshops.Startdate,
            db.workshops.Enddate,
            db.workshops.Starttime,
            db.workshops.Endtime,
            db.workshops.auth_teacher_id,
            db.workshops.auth_teacher_id2,
            db.workshops.Preview,
            db.workshops.Description,
            db.workshops.school_levels_id,
            db.workshops.school_locations_id,
            db.workshops.picture,
            db.workshops.thumbsmall,
            db.workshops.thumblarge,
            db.workshops_products.Price
        ]

        query = '''
        SELECT ws.id,
               ws.Name,
               ws.Tagline,
               ws.Startdate,
               ws.Enddate,
               ws.Starttime,
               ws.Endtime,
               ws.auth_teacher_id,
               ws.auth_teacher_id2,
               ws.Preview,
               ws.Description,
               ws.school_levels_id,
               ws.school_locations_id,
               ws.picture,
               ws.thumbsmall,
               ws.thumblarge,
               wsp.Price
        FROM workshops ws
        LEFT JOIN
            ( SELECT id, workshops_id, Price FROM workshops_products
              WHERE FullWorkshop = 'T' ) wsp
            ON ws.id = wsp.workshops_id
        WHERE ws.id > 0
              {where_filter}
        ORDER BY {orderby_sql}
        '''.format(orderby_sql = orderby_sql,
                   where_filter = where_filter)

        rows = db.executesql(query, fields=fields)

        return rows


    def get_workshops_list(self):
        '''
            Returns list of workshops
        '''
        rows = self.get_workshops_rows().as_list()


    def _get_workshops_shop(self):
        """
            Format list of workshops in a suitable way for the shop
        """
        def new_workshop_month():
            _class = 'workshops-list-month'

            return DIV(H2(last_day_month.strftime('%B %Y'), _class='center'), _class=_class)

        request = current.request
        os_gui = current.globalenv['os_gui']
        T = current.T
        TODAY_LOCAL = current.TODAY_LOCAL

        rows = self.get_workshops_rows()

        current_month = TODAY_LOCAL
        last_day_month = get_last_day_month(current_month)

        workshops_month = new_workshop_month()
        workshops_month_body = DIV(_class='box-body')


        workshops = DIV()

        for i, row in enumerate(rows):
            repr_row = list(rows[i:i + 1].render())[0]

            more_info = os_gui.get_button('noicon',
                URL('event', vars={'wsID':row.workshops.id}),
                title=T('More info...'),
                btn_class='btn-link',
                btn_size='',
                _class='workshops-list-workshop-more-info')

            # Check if we're going into a later month
            if row.workshops.Startdate > last_day_month:
                if len(workshops_month_body) >= 1:
                    # check if we have more in the month than just the title (the 1 in len())
                    workshops_month.append(DIV(workshops_month_body, _class='box box-solid'))
                    workshops.append(workshops_month)
                last_day_month = get_last_day_month(row.workshops.Startdate)
                workshops_month = new_workshop_month()
                workshops_month_body = DIV(_class='box-body')

            startdate = SPAN(row.workshops.Startdate.strftime('%d %B').lstrip("0").replace(" 0", " "), _class='label_date')
            enddate = ''
            if not row.workshops.Startdate == row.workshops.Enddate:
                enddate = SPAN(row.workshops.Enddate.strftime('%d %B').lstrip("0").replace(" 0", " "), _class='label_date')
            workshop = DIV(
                DIV(DIV(DIV(repr_row.workshops.thumblarge, _class='workshops-list-workshop-image center'),
                        _class='col-xs-12 col-sm-12 col-md-3'),
                        DIV(A(H3(row.workshops.Name), _href=URL('shop', 'event', vars={'wsID':row.workshops.id})),
                            H4(repr_row.workshops.Tagline),
                            DIV(os_gui.get_fa_icon('fa-calendar-o'), ' ',
                                startdate, ' ',
                                repr_row.workshops.Starttime, ' - ',
                                enddate, ' ',
                                repr_row.workshops.Endtime,
                                _class='workshops-list-workshop-date'),
                            DIV(os_gui.get_fa_icon('fa-user-o'), ' ', repr_row.workshops.auth_teacher_id, _class='workshops-list-workshop-teacher'),
                            DIV(os_gui.get_fa_icon('fa-map-marker'), ' ', repr_row.workshops.school_locations_id, _class='workshops-list-workshop-location'),
                            BR(),
                            more_info,
                            _class='col-xs-12 col-sm-12 col-md-9 workshops-list-workshop-info'),
                        _class=''),
                _class='workshops-list-workshop col-md-8 col-md-offset-2 col-xs-12')

            workshops_month_body.append(workshop)

            # if we're at the last row, add the workshops to the page
            if i + 1 == len(rows):
                workshops_month.append(DIV(workshops_month_body, _class='box box-solid'))
                workshops.append(workshops_month)

        return workshops


    def get_workshops_shop(self):
        """
            Use caching when not running as test to return the workshops list in the shop
        """
        web2pytest = current.globalenv['web2pytest']
        request = current.request
        auth = current.auth

        # Don't cache when running tests
        if web2pytest.is_running_under_test(request, request.application):
            rows = self._get_workshops_shop()
        else:
            cache = current.cache
            CACHE_LONG = current.globalenv['CACHE_LONG']
            cache_key = 'openstudio_workshops_workshops_schedule_shop'

            rows = cache.ram(cache_key , lambda: self._get_workshops_shop(), time_expire=CACHE_LONG)

        return rows


