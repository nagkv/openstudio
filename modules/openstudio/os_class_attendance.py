# -*- coding: utf-8 -*-

from gluon import *


class ClassAttendance:
    """
        This class collects functions related to a class attendance record
    """
    def __init__(self, clattID):
        db = current.db
        self.id = clattID
        self.row = db.classes_attendance(clattID)


    def get_datetime_start(self):
        """
            Returns datetime object of class start
        """
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
        """
            Calculates datetime of latest cancellation possibility
        """
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
        """
             Can we still cancel this booking?
             Allow cancellation when within the configures hours limit and not already attending
        """
        NOW_LOCAL = current.NOW_LOCAL
        cancel_before = self.get_cancel_before()

        if NOW_LOCAL < cancel_before and not self.row.BookingStatus == 'attending':
            return True
        else:
            return False


    def set_status_cancelled(self, force=False):
        """
            Set status cancelled
        """
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