#!/usr/bin/python3 

import feedparser
import datetime
import hashlib 
from contextlib import closing
from sqlitedict import SqliteDict

import smtplib 
from email.mime.multipart import MIMEMultipart 
from email.mime.text import MIMEText 
from email.mime.base import MIMEBase 
from email import encoders 

import time

config="/home/rssmon/list.txt"
db = "/home/rssmon/db.sqlite"
email_config="/home/rssmon/email.conf"

with open(email_config, 'r') as f: 
	config_line = f.read().rstrip()
	items = config_line.split(',')
	toaddr = items[0]
	fromaddr = items[1]
	sender_passwd = items[2]

if toaddr is None or toaddr == "" or fromaddr is None or fromaddr == "" or sender_passwd is None or sender_passwd == "":
	print("Email config is missing")
	exit()


def get_feed_configs(): 
	ret = []

	with open(config, 'r') as f: 
		lines = f.readlines()

	for line in lines: 
		items = line.rstrip().split(',')
		rss = items[0]
		keywords = items[1:]
		ret.append({"rss": rss, "keywords": keywords})

	return ret


def any_in(keywords, string):
	ret = True
	if keywords is None or len(keywords) == 0: 
		return True
	lc = string.lower()
	for kw in keywords: 
		if kw.lower() in lc: 
			return True
	return False

def get_or_empty(d, k, default=""):
	if k in d: 
		return d[k]
	return default

def get_new_feed_entries(url, keywords, db_dict):
	ret = []
	d = feedparser.parse(url)
	if 'entries' in d:
		for entry in d['entries']:
			title = get_or_empty(entry, 'title')
			summary = get_or_empty(entry, 'summary')
			link = get_or_empty(entry, 'link')
			published_raw = get_or_empty(entry, 'published')
			published = get_or_empty(entry, 'published_parsed', None)
			published = datetime.datetime(published.tm_year, published.tm_mon, published.tm_mday, published.tm_hour, published.tm_min, published.tm_sec) \
						if published is not None \
						else datetime.datetime(1970, 1, 1, 0, 0, 0)
		
			if 'content' in entry: 
				content = "" 
				for citem in entry['content']: 
					if 'value' in citem: 
						content = content + "" + citem['value']
				if content != "": 
					summary = content

			if title == "" and summary == "": 
				continue

			if any_in(keywords, title) or any_in(keywords, summary):
				content_hash = hashlib.sha224((title + "-" + summary + "-" + link + "-" + published_raw).encode('utf-8')).hexdigest()

				if content_hash not in db_dict:
					ret.append([title, link, published_raw, published, summary, content_hash])

	return (ret, d['feed']['title'])


def generate_email_message(rss_title, rss_items):
	ret = None 

	msg = MIMEMultipart("alternative") 
	msg['From'] = fromaddr 
	msg['To'] = toaddr
	if len(rss_items) == 1: 
		msg['Subject'] = "rssmon: {0}: {1}".format(rss_title, rss_items[0][0])
	else: 
		msg['Subject'] = "rssmon: {0}: {1} new items".format(rss_title, len(rss_items))

	body = "<html><header></header><body><h2>New feed entries for{}</h2>".format(rss_title)

	for item in rss_items:
		title, link, published_raw, published, summary, content_hash = item
		body = body + """
			<a href="{link}"><h3>{title}</h3></a>
			<b>Publication date: {pubdate}</b>
			<br/>
			{summary}
			<br/>
			<a href="{link2}">Read More</a>
			<br/>
			""".format(title=title, link=link, pubdate=str(published), summary=summary, link2=link) 
	body = body + "</body></html>"

	msg.attach(MIMEText(body, 'html')) 

	return msg.as_string()

def send_email_messages(messages):
	ret = None 
	
	s = smtplib.SMTP('smtp.gmail.com', 587) 
	s.starttls() 
	s.login(fromaddr, sender_passwd) 
	 
	for msg in messages: 
		s.sendmail(fromaddr, toaddr, msg) 
		time.sleep(0.3)
	s.quit() 

	return True

cfgs = get_feed_configs()

with SqliteDict(db) as db_dict:

	messages = []
	hashes = []

	for cfg in cfgs: 
		items, title = get_new_feed_entries(cfg['rss'], cfg['keywords'], db_dict)
		if items is None or len(items) == 0: 
			continue
		msg = generate_email_message(title, items)
		if msg is not None and msg != "": 
			messages.append(msg)
			for item in items: 
				hashes.append(item[5])

	if len(messages) > 0 and send_email_messages(messages):
		for h in hashes: 
			db_dict[h] = 1
		db_dict.commit()
