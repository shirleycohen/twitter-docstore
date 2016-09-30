#! /usr/bin/env python

# twitter_xproto - Load tweets into MySQL document store from a twitter search

import mysqlx
import sys
import json
import logging
from twython import TwythonStreamer
from Queue import Queue 
from threading import Thread
from time import sleep

#logging level
logging.basicConfig( level = 'INFO' )

# only command-line arg is the search term ('mysql', usually)
if( len( sys.argv ) < 2 ):
	print 'Please supply a search term'
	sys.exit(2)

# GLOBALS - for now
term = sys.argv[1]
tweet_queue = Queue()

# read twitter account info from a JSON file 
# in the current dir
cnf = open( "./twitter_auth.cnf", "r" )
twitter_auth = json.load(cnf)
cnf.close()


class TwitterStreamer(TwythonStreamer):
	def on_error( self, status_code, msg ):
		logging.critical( 'Error code: ' + str( status_code) )
		logging.critical( str( msg ) )
		return False

	def on_success( self, tweet ):
		tweet_queue.put( tweet )
		return True

	def start( self): # was __call__ for the thread...
		logging.info( 'Starting stream' )
		self.statuses.filter( track = term )

	def stop( self ):
		self.disconnect()


class TweetWriter( Thread ):

	def __init__( self, queue, search_term ):
		Thread.__init__(self)
		self.term = search_term
		self.name = self.term + '_Writer'+ self.name
		self.tweet_queue = queue
		self.inserts = 0
		self.running = True

	def insert( self, tweet ):
		db = self.connect()
		db.add( tweet ).execute()
		self.inserts += 1

	def connect( self ):
		my_db = mysqlx.get_session( {\
		'host': '10.0.2.2', 'port': 33060,\
		'user': 'twt_sel', 'password': 'chester'}\
		).get_schema( 'twitter_mysql')
		#logging.info( 'Connecting to DB' )
		return my_db.get_collection( self.term + '_tweets' ) 
	
	def stop( self ):
		self.running = False
		logging.info( "Thread %s ending", self.name )
		logging.info( "Inserted %d tweets", self.inserts )
	
	def run( self ):
		logging.info( "TweetWriter %s starting", self.name ) 
		while self.running == True:
			if( self.tweet_queue.empty() != True ):
				tweet = self.tweet_queue.get()
				self.insert( tweet )
				self.inserts += 1
				logging.info( tweet[u'text']  )
			else:
				sleep(5)


# connect to twitter
twy = TwitterStreamer( app_key = twitter_auth['consumer_key'], \
	app_secret = twitter_auth['consumer_secret'], \
	oauth_token = twitter_auth['access_token_key'], \
	oauth_token_secret= twitter_auth['access_token_secret']) 

twy.daemon = False
w1 = TweetWriter(tweet_queue, term )
w2 = TweetWriter(tweet_queue, term )
try:
	w1.start()
	w2.start()
	twy.start()
except KeyboardInterrupt:
	print 'Received SIGINT'
	twy.stop()
	sleep(1)
	w1.stop()
	w2.stop()

logging.info( 'All done' )
if( tweet_queue.qsize() > 0 ):
	logging.warning( "Queue size at %d", tweet_queue.qsize() )
	with open( "./tweets.txt", "w" ) as outfile:
		while not tweet_queue.empty():
			json.dump( tweet_queue.get(), outfile )
			outfile.write( "\n" )
		outfile.close()

sys.exit(0)