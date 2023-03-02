"""
MIT License

Copyright (C) 2023 ROCKY4546
https://github.com/rocky4546

This file is part of Cabernet

Permission is hereby granted, free of charge, to any person obtaining a copy of this software
and associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software
is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.
"""

import random

import lib.common.exceptions as exceptions
from lib.plugins.plugin_obj import PluginObj

from .tv123_instance import TV123Instance
from ..lib import translations


class TV123(PluginObj):

    def __init__(self, _plugin, _plugins):
        super().__init__(_plugin)

        self.plugins = _plugins

        if self.config_obj.data[self.namespace.lower()]['epg-plugin'] == 'ALL':
            self.enable_instance('TVGuide', 'default')
        for inst in _plugin.instances:
            self.instances[inst] = TV123Instance(self, inst)
        self.unc_tv123_base = self.uncompress(translations.tv123_base)
        self.unc_tv123_additional_channels = self.uncompress(translations.tv123_additional_channels)
        self.unc_tv123_wp_more_ch_cmd = self.uncompress(translations.tv123_wp_more_ch_cmd)
        self.unc_tv123_stream_channel = self.uncompress(translations.tv123_stream_channel)
        self.unc_tv123_referer = self.uncompress(translations.tv123_referer)
        self.unc_tv123_ch_epg = self.uncompress(translations.tv123_ch_epg)
        self.unc_tv123_agpigee_referer = self.uncompress(translations.tv123_agpigee_referer)
        self.unc_tv123_prog_details = self.uncompress(translations.tv123_prog_details)
        self.unc_tv123_image = self.uncompress(translations.tv123_image)

    def scan_channels(self, _instance=None):
        """
        Called from the scheduler
        Requests a stream for each of the disabled channels to see if they
        are up
        """
        try:
            if not self.enabled:
                self.logger.debug('{} Plugin disabled, not scanning channels'
                                  .format(self.plugin.name))
                return False
            if _instance is None:
                for key, instance in self.instances.items():
                    instance.scan_channels()
            else:
                self.instances[_instance].scan_channels()
            return True
        except exceptions.CabernetException:
            self.logger.debug('CabernetException channel scan task: Setting plugin {} to disabled'
                              .format(self.plugin.name))
            self.enabled = False
            self.plugin.enabled = False
            return False

    def scheduler_tasks(self):
        sched_epg_local1_hours = 1
        sched_epg_local2_hours = 12
        sched_epg_hours = self.utc_to_local_time(0)
        sched_epg_mins = random.randint(1, 55)
        sched_epg_local1 = '{:0>2d}:{:0>2d}'.format(sched_epg_local1_hours, sched_epg_mins)
        sched_epg_local2 = '{:0>2d}:{:0>2d}'.format(sched_epg_local2_hours, sched_epg_mins)
        sched_epg = '{:0>2d}:{:0>2d}'.format(sched_epg_hours, sched_epg_mins)
        sched_ch_hours = self.utc_to_local_time(23)
        sched_ch_mins = random.randint(1, 55)
        sched_ch = '{:0>2d}:{:0>2d}'.format(sched_ch_hours, sched_ch_mins)
        sched_scan_local_hours = 1
        sched_scan_mins = random.randint(1, 55)
        sched_scan = '{:0>2d}:{:0>2d}'.format(sched_scan_local_hours, sched_scan_mins)

        if self.scheduler_db.save_task(
                'Channels',
                'Refresh {} Channels'.format(self.namespace),
                self.name,
                None,
                'refresh_channels',
                20,
                'inline',
                'Pulls channel lineup from {}'.format(self.namespace)
        ):
            self.scheduler_db.save_trigger(
                'Channels',
                'Refresh {} Channels'.format(self.namespace),
                'startup')
            self.scheduler_db.save_trigger(
                'Channels',
                'Refresh {} Channels'.format(self.namespace),
                'daily',
                timeofday=sched_ch
            )
        if self.scheduler_db.save_task(
                'EPG',
                'Refresh {} EPG'.format(self.namespace),
                self.name,
                None,
                'refresh_epg',
                10,
                'thread',
                'Pulls channel program data from {}'.format(self.namespace)
        ):
            self.scheduler_db.save_trigger(
                'EPG',
                'Refresh {} EPG'.format(self.namespace),
                'startup')
            # update after midnight local time
            self.scheduler_db.save_trigger(
                'EPG',
                'Refresh {} EPG'.format(self.namespace),
                'daily',
                timeofday=sched_epg
            )
            # update after midnight gmt time
            self.scheduler_db.save_trigger(
                'EPG',
                'Refresh {} EPG'.format(self.namespace),
                'daily',
                timeofday=sched_epg_local1
            )
            # update after noon gmt time
            self.scheduler_db.save_trigger(
                'EPG',
                'Refresh {} EPG'.format(self.namespace),
                'daily',
                timeofday=sched_epg_local2
            )
        if self.scheduler_db.save_task(
                'Unique',
                'Scan {} Disabled Channels'.format(self.namespace),
                self.name,
                None,
                'scan_channels',
                5,
                'thread',
                'Scans disabled channels to see if they are up'
        ):
            self.scheduler_db.save_trigger(
                'Unique',
                'Scan {} Disabled Channels'.format(self.namespace),
                'weekly',
                dayofweek='Sunday',
                timeofday=sched_scan
            )
