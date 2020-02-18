# -*- coding: utf-8 -*-

from gluon import *

def set_version():
    """
        Set version of current OpenStudio release
    """
    db = current.db
    cache_clear_sys_properties = current.globalenv['cache_clear_sys_properties']

    row = db.sys_properties(Property='Version')
    version = '2020.02'
    if not row:
        db.sys_properties.insert(Property='Version', PropertyValue=version)
    else:
        row.PropertyValue = version
        row.update_record()

    # set release
    row = db.sys_properties(Property='VersionRelease')
    release = '0'
    if not row:
        db.sys_properties.insert(Property='VersionRelease',
                                 PropertyValue=release)
    else:
        row.PropertyValue = release
        row.update_record()

    cache_clear_sys_properties()