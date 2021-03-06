# -*- coding: utf-8 -*-

import os
import csv

from trello import TrelloClient
import logging

import httplib2
import datetime
import arrow


class TrelloCollector(object):
    """
    Class representing all Trello information required to do the SysDesEng reporting.
    """

    def __init__(self, report_config, trello_secret):
        self.logger = logging.getLogger(__name__)
        self.client = TrelloClient(api_key = trello_secret[':consumer_key'],
                                   api_secret = trello_secret[':consumer_secret'],
                                   token = trello_secret[':oauth_token'],
                                   token_secret = trello_secret[':oauth_token_secret'])

        #Extract report configuration parameters
        trello_sources = report_config[':trello_sources'];
        #self.report_parameters = report_config[':output_metadata'];
        gen_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        self.content = { ':output_metadata' : {
                              ':gen_date': gen_date, #Report name is built as :report_name + gen_date (where :report_name is taken from the config)
                              ':trello_sources': {
                                 ':boards':{},
                                 ':lists': {},
                                 ':cards': [] }}}

        self.load_config(trello_sources, self.content[':output_metadata'][':trello_sources'])
        self.logger.debug("Report output metadata: %s" % (self.content[':output_metadata']))

    def load_config(self, config_src, report_metadata):
        """ load all config data related to trello sources and structure them in the report_metadata"""
        for card_type in config_src.keys(): #card_type is project|assignment|epic
            for board_t in config_src[card_type].keys():
                board_id = config_src[card_type][board_t][':board_id']
                if not board_id in report_metadata: # initialize if the board wasn't present during the iterations over other card_type's
                    if not board_id in report_metadata[':boards']:
                        report_metadata[':boards'][board_id] = {};
                    report_metadata[':boards'][board_id][':board_id'] = config_src[card_type][board_t][':board_id'] #copy board id
                    report_metadata[':boards'][board_id][':board_name'] = board_t
                    if not ':lists' in report_metadata[':boards'][board_id]:
                        report_metadata[':boards'][board_id][':lists'] = []

                #iterate through all the lists and populate them
                for list_t in config_src[card_type][board_t][':lists'].keys():
                    self.logger.debug("Adding board %s, list %s to the report" % (config_src[card_type][board_t][':board_id'], config_src[card_type][board_t][':lists'][list_t]))
                    list_id = config_src[card_type][board_t][':lists'][list_t]
                    report_metadata[':lists'][list_id] = {};
                    report_metadata[':lists'][list_id][':list_id'] = list_id
                    report_metadata[':lists'][list_id][':completed'] = False;
                    report_metadata[':lists'][list_id][':card_type'] = card_type;
                    report_metadata[':lists'][list_id][':board_id'] = board_id
                    report_metadata[':boards'][board_id][':lists'].append(list_id)
                if ':done_lists' in config_src[card_type][board_t]:
                    for list_t in config_src[card_type][board_t][':done_lists'].keys():
                        self.logger.debug("Adding board %s, Done list %s to the report" % (config_src[card_type][board_t][':board_id'], config_src[card_type][board_t][':done_lists'][list_t]))
                        list_id = config_src[card_type][board_t][':done_lists'][list_t]
                        report_metadata[':lists'][list_id] = {};
                        report_metadata[':lists'][list_id][':list_id'] = list_id
                        report_metadata[':lists'][list_id][':completed'] = True;
                        report_metadata[':lists'][list_id][':card_type'] = card_type;
                        report_metadata[':lists'][list_id][':board_id'] = board_id
                        report_metadata[':boards'][board_id][':lists'].append(list_id)

    def list_boards(self):
        syseng_boards = self.client.list_boards()
        for board in syseng_boards:
            for tlist in board.all_lists():
                self.logger.info('board name: %s is here, board ID is: %s; list %s is here, list ID is: %s' % (board.name, board.id, tlist.name, tlist.id)) 

    def parse_trello(self, deep_scan):
        """
        :deep_scan: If deep_scan is True the scan will traverse actions, otherwise just a light scan(much faster)
        Main function to parse all Trello boards and lists.
        """
        trello_sources = self.content[':output_metadata'][':trello_sources'];
        self.logger.debug('The sources are %s' % (trello_sources))

        for board_id in trello_sources[':boards'].keys():
            tr_board = self.client.get_board(board_id);
            tr_board.fetch(); # get all board properties
            members = [ (m.id, m.full_name) for m in tr_board.get_members()];
            trello_sources[':boards'][board_id][':members'] = members;
            self.logger.info('----- querying board %s -----' % (trello_sources[':boards'][board_id][':board_name']))
            self.logger.debug('Board members are %s' % (trello_sources[':boards'][board_id][':members']))

            #trello_sources[board_id][':cards'] = []
            cards = tr_board.get_cards();

    
            for card in cards:
                card_content = {}
                card_content[':name'] = card.name
                card_content[':id'] = card.id
                card_content[':members'] = []
                card_content[':board_id'] = tr_board.id
                for member_id in card.member_ids:
                    for (m_id, m_full_name) in members:
                        if member_id == m_id :
                           card_content[':members'].append((m_id,m_full_name))
                card_content[':desc'] = card.desc
                card_content[':short_url'] = card.url
                card_content[':labels'] = [(label.name,label.color) for label in card.labels]
                #self.logger.debug('Card: {0} | LABELES are {1}'.format(card_content[':name'], card_content[':labels']))
                card_content[':board_name'] = tr_board.name
                card_content[':list_id'] = card.list_id
                if card.due:
                    card_content[':due_date'] = arrow.get(card.due).format('YYYY-MM-DD HH:mm:ss')
                trello_sources[':cards'].append(card_content);

            self.logger.debug('%s cards were collected' % (len(cards)))

            tr_board.fetch_actions(action_filter="commentCard,updateCard:idList,createCard,copyCard,moveCardToBoard,convertToCardFromCheckItem",action_limit=1000);
            trello_sources[':boards'][board_id][':actions'] = sorted(tr_board.actions,key=lambda act: act['date'], reverse=True)
            self.logger.debug('%s actions were collected' % (len(trello_sources[':boards'][board_id][':actions'])))
            #self.logger.debug('Oldest action is %s' % (trello_sources[':boards'][board_id][':actions'][-1]))

            tr_lists = tr_board.all_lists()
            for tr_list in tr_lists:
                if tr_list.id in trello_sources[':lists']:
                    trello_sources[':lists'][tr_list.id][':name'] = tr_list.name;
            self.logger.info('the lists are %s' % (tr_lists))

        return self.content


    def parse_card_details(self, card_id):
        card = card_details.CardDetails(card_id, self.client, self.content[':output_metadata'])
        details = card.fill_details();
        #self.logger.debug('Card\'s details are: %s' % (details))
        return details
