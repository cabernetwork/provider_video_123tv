# pylama:ignore=E722
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

import datetime
import json

import lib.common.utils as utils
from lib.db.db_epg_programs import DBEpgPrograms
from lib.db.db_channels import DBChannels
from lib.plugins.plugin_epg import PluginEPG


class EPG(PluginEPG):

    def __init__(self, _instance_obj):
        super().__init__(_instance_obj)
        self.db_programs = DBEpgPrograms(self.config_obj.data)
        self.db_channels = DBChannels(self.config_obj.data)
        self.provider_channel_epg_dict = {}
        self.current_time = datetime.datetime.now(datetime.timezone.utc)

    def dates_to_pull(self):
        """
        123tv provides upto 3 days of EPG.  Each channel is different.
        """
        return [0, 1, 2], []

    def refresh_programs(self, _epg_day, use_cache=True):
        self.current_time = datetime.datetime.now(datetime.timezone.utc)
        midnight = self.current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        start_time = midnight + datetime.timedelta(days=_epg_day)
        start_seconds = int(start_time.timestamp())
        start_date = start_time.date()

        program_list = []
        program_list = self.get_fullday_programs(program_list, start_seconds)
        if program_list:
            self.db.save_program_list(self.plugin_obj.name, self.instance_key, start_date, program_list)
            self.logger.debug('Refreshed EPG data for {}:{} day {}'
                              .format(self.plugin_obj.name, self.instance_key, start_date))
        program_list = None        # to help with garbage collection
        return

    def get_fullday_programs(self, _program_list, _start_seconds):
        """
        Returns a days (from midnight to midnight UTC) of programs for all channels
        enabled.  Also adds epg data for any channel with no epg data.
        Will return the original _program_list passed in if no epg data was found
        """
        epg_list = {}
        missing_ch_list = []
        prog_ids = {}
        is_data_found = False
        current_time_sec = self.current_time.timestamp()
        channel_list = self.db_channels.get_channels(self.plugin_obj.name, self.instance_key)
        for ch in channel_list.values():
            ch_id = ch[0]['uid']
            epg_id = ch[0]['json']['epg_id']
            if not ch[0]['enabled']:
                # skip if channel is disabled
                continue
            if epg_id is None:
                # if no epg is found from 123tv, add to missing epg list
                missing_ch_list.append(ch_id)
                continue

            # maintain memory cache of channel list for faster processing
            if epg_id not in self.provider_channel_epg_dict:
                # get provider epg data and cache it.
                provider_ch_epg = self.get_uri_data(self.plugin_obj.unc_tv123_base
                                                    + self.plugin_obj.unc_tv123_ch_epg.format(epg_id))
                if provider_ch_epg is None:
                    continue
                self.provider_channel_epg_dict[epg_id] = provider_ch_epg
            else:
                provider_ch_epg = self.provider_channel_epg_dict[epg_id]
            epg_day = provider_ch_epg['items'].get(str(_start_seconds))
            if epg_day is None:
                # no data available for day requested
                if is_data_found:
                    # epg for this day has been found for other channels, so 
                    # add to missing channel list
                    missing_ch_list.append(ch_id)
                continue

            self.logger.debug('{}:{} Processing EPG for Channel {}'
                              .format(self.plugin_obj.name, self.instance_key, ch[0]['display_name']))

            # are there any programs that are current or in the future?
            # if none are, then add to missing list
            is_new_data = False
            for prog in epg_day:
                if prog['end_timestamp'] > current_time_sec:
                    is_new_data = True
                    break
            if not is_new_data:
                missing_ch_list.append(ch_id)
                continue

            is_data_found = True
            # create the list of events to add to the epg for the day
            for prog in epg_day:
                start_time = utils.tm_local_parse(prog['start_timestamp'] * 1000)
                key = (ch_id, start_time)
                if key not in epg_list.keys():
                    epg_list[key] = {
                        'id': prog['id'],
                        'channelId': ch_id,
                        'start': prog['start_timestamp'],
                        'end': prog['end_timestamp']
                    }
                    prog_ids[prog['id']] = None

        self.logger.info('{}:{} Processing {} Programs for day'
                         .format(self.plugin_obj.name, self.instance_key, len(prog_ids.keys())))
        for listing_data in epg_list.values():
            ch_data = channel_list[str(listing_data['channelId'])][0]
            program_json = self.get_program(ch_data,
                                            listing_data)
            if program_json is not None:
                _program_list.append(program_json)

        # add default epg for all channels having no epg data
        if _program_list:
            for ch_id in missing_ch_list:
                ch_data = channel_list[ch_id][0]
                program_json = self.get_missing_program(ch_data,
                                                        ch_id, _start_seconds)
                if program_json is not None:
                    _program_list.extend(program_json)

        return _program_list

    def get_missing_program(self, _ch_data, _ch_id, _start_seconds):
        """
        For a channel, will create a set of program events 1 hour apart
        for 24 hours based on the _start_seconds starting point. Most of the 
        event data are defaults.
        """
        if not _ch_data['enabled']:
            return None
        self.logger.debug('{}:{} Adding minimal EPG data for channel {}'
                          .format(self.plugin_obj.name, self.instance_key, _ch_id))
        event_list = []
        start_date = datetime.datetime.fromtimestamp(_start_seconds, datetime.timezone.utc)
        for incr_hr in range(0, 24):
            start_time = start_date + datetime.timedelta(hours=incr_hr)
            start_fmt = utils.tm_local_parse(start_time.timestamp() * 1000)
            end_time = start_time + datetime.timedelta(hours=1)
            end_fmt = utils.tm_local_parse(end_time.timestamp() * 1000)
            dur_min = 60
            event = {'channel': _ch_id, 'progid': None, 'start': start_fmt, 'stop': end_fmt,
                     'length': dur_min, 'title': _ch_data['display_name'], 'subtitle': None, 'entity_type': None,
                     'desc': 'Unavailable', 'short_desc': 'Unavailable',
                     'video_quality': None, 'cc': None, 'live': None, 'finale': None,
                     'premiere': None, 'air_date': None, 'formatted_date': None, 'icon': None,
                     'rating': None, 'is_new': None, 'genres': None,
                     'directors': None, 'actors': None,
                     'season': None, 'episode': None, 'se_common': None, 'se_xmltv_ns': None,
                     'se_progid': None
                     }
            event_list.append(event)
        return event_list

    def get_program(self, _ch_data, _event_data):
        """
        Takes a single channel data with the program event and 
        returns a json program event object
        Assumes the prog_id data is already present in the
        epg program database
        """
        if not _ch_data['enabled']:
            return None
        prog_id = _event_data['id']
        if self.config_obj.data[self.plugin_obj.namespace.lower()]['epg-plugin'] == 'ALL':
            prog_details = self.plugin_obj.plugins['TVGuide'].plugin_obj \
                .get_program_info_ext(prog_id)
        else:
            return None
        if len(prog_details) == 0:
            self.logger.warning('Program error: EPG program details missing {} {}'
                                .format(self.plugin_obj.name, prog_id))
            return None

        prog_details = json.loads(prog_details[0]['json'])

        start_time = utils.tm_local_parse(
            (_event_data['start']
             + self.config_obj.data[self.config_section]['epg-start_adjustment'])
            * 1000)
        end_time = utils.tm_local_parse(
            (_event_data['end']
             + self.config_obj.data[self.config_section]['epg-end_adjustment'])
            * 1000)
        dur_min = int((_event_data['end'] - _event_data['start']) / 60)
        if not prog_details['date']:
            if prog_details['year']:
                air_date = str(prog_details['year'])
                formatted_date = str(air_date)
            else:
                air_date = None
                formatted_date = None
        else:
            air_date_msec = int(prog_details['date'])
            air_date = utils.date_parse(air_date_msec, '%Y%m%d')
            formatted_date = utils.date_parse(air_date_msec, '%Y/%m/%d')

        sid = str(_event_data['channelId'])
        title = prog_details['title']
        entity_type = prog_details['type']

        if prog_details['desc']:
            description = prog_details['desc']
        else:
            description = 'Unavailable'
        if prog_details['short_desc']:
            short_desc = prog_details['short_desc']
        else:
            short_desc = description

        if prog_details['episode']:
            episode = prog_details['episode'] + self.episode_adj
        else:
            episode = None
        season = prog_details['season']

        if (season is None) and (episode is None):
            se_common = None
            se_xmltv_ns = None
            se_prog_id = None
        elif (season is not None) and (episode is not None):
            se_common = 'S%02dE%02d' % (season, episode)
            se_xmltv_ns = ''.join([str(season - 1), '.', str(episode - 1), '.0/1'])
            se_prog_id = None
        elif (season is None) and (episode is not None):
            se_common = None
            se_xmltv_ns = None
            se_prog_id = None
        else:  # (season is not None) and (episode is None):
            se_common = 'S%02dE%02d' % (season, 0)
            se_xmltv_ns = ''.join([str(season - 1), '.', '0', '.0/1'])
            se_prog_id = None

        if prog_details['subtitle']:
            if season and episode:
                subtitle = 'S%02dE%02d ' % (season, episode)
            elif episode:
                subtitle = 'E%02d ' % episode
            else:
                subtitle = ''
            subtitle += prog_details['subtitle']
        else:
            subtitle = None

        rating = prog_details['rating']

        video_quality = None
        cc = False
        live = None
        is_new = None
        finale = None
        premiere = None

        icon = prog_details['image']
        genres = prog_details['genres']
        directors = None
        actors = None

        json_result = {'channel': sid, 'progid': prog_id, 'start': start_time, 'stop': end_time,
                       'length': dur_min, 'title': title, 'subtitle': subtitle, 'entity_type': entity_type,
                       'desc': description, 'short_desc': short_desc,
                       'video_quality': video_quality, 'cc': cc, 'live': live, 'finale': finale,
                       'premiere': premiere,
                       'air_date': air_date, 'formatted_date': formatted_date, 'icon': icon,
                       'rating': rating, 'is_new': is_new, 'genres': genres, 'directors': directors, 'actors': actors,
                       'season': season, 'episode': episode, 'se_common': se_common, 'se_xmltv_ns': se_xmltv_ns,
                       'se_progid': se_prog_id}
        return json_result
