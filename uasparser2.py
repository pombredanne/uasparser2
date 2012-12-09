"""
userparse2
	By Jure Ham (jure.ham@zemanta.com)

Based on:
	A python version of http://user-agent-string.info/download/UASparser

	By Hicro Kee (http://hicrokee.com)
	email: hicrokee AT gmail DOT com

	Modified by Michal Molhanec http://molhanec.net

Usage:
	from uasparser import UASparser

	uas_parser = UASparser('/path/to/your/cache/folder')

	result = uas_parser.parse('YOUR_USERAGENT_STRING',entire_url='ua_icon,os_icon') #only 'ua_icon' or 'os_icon' or both are allowed in entire_url
"""

from collections import OrderedDict
import urllib2
import os
import re
try:
	import cPickle as pickle
except:
	import pickle

class UASException(Exception):
	pass

class UASparser:

	ini_url  = 'http://user-agent-string.info/rpc/get_data.php?key=free&format=ini'
	info_url = 'http://user-agent-string.info'

	cache_file_name = 'uasparser2_cache'
	cache_dir = ''
	data = None

	mem_cache = OrderedDict()
	mem_cache_size = 1000

	# for testing only
	cache_hit = 0
	cache_all = 0

	empty_result = {
		'typ':'unknown',
		'ua_family':'unknown',
		'ua_name':'unknown',
		'ua_url':'unknown',
		'ua_company':'unknown',
		'ua_company_url':'unknown',
		'ua_icon':'unknown.png',
		'ua_info_url':'unknown',
		'os_family':'unknown',
		'os_name':'unknown',
		'os_url':'unknown',
		'os_company':'unknown',
		'os_company_url':'unknown',
		'os_icon':'unknown.png',
	}

	def __init__(self, cache_dir=None, mem_cache_size=1000):
		"""
		Create an UASparser to parse useragent strings.
		cache_dir should be appointed or set to the path of program by default
		"""
		self.cache_dir = cache_dir or os.path.abspath( os.path.dirname(__file__) )
		if not os.access(self.cache_dir, os.W_OK):
			raise UASException("Cache directory %s is not writable.")
		self.cache_file_name = os.path.join( self.cache_dir, self.cache_file_name)

		self.mem_cache_size = mem_cache_size

		self.loadData()

	def parse(self, useragent):
		"""
		Get the information of an useragent string
		Args:
			useragent: String, an useragent string
			entire_url: String, write the key labels which you want to get an entire url split by comma, expected 'ua_icon' or 'os_icon'.
		"""

		def match_robots(data, result):
			for test in data['robots']:
				if test['ua'] == useragent:
					result += test['details']
					return True
			return False

		def match_browser(data, result):
			for test in data['browser']['reg']:
				test_rg = test['re'].findall(useragent)
				if test_rg:
					browser_version = test_rg[0]
					result += data['browser']['details'][test['details_key']]
					return True, browser_version
			return False, None

		def match_os(data, result):
			for test in data['os']['reg']:
				if test['re'].findall(useragent):
					result += data['os']['details'][test['details_key']]
					return True
			return False

		def add_to_cache(result_dict, matched):
			if matched:
				self.cache_hit += 1
				del self.mem_cache[useragent]
			self.cache_all += 1

			self.mem_cache[useragent] = result_dict

			if len(self.mem_cache) > self.mem_cache_size:
				self.mem_cache.popitem(last=False)

		def get_from_cache():
			if useragent in self.mem_cache:
				return True, self.mem_cache[useragent]
			else:
				return False, None

		if not useragent:
			raise UASException("Excepted argument useragent is not given.")

		matched_cache, result_dict = get_from_cache()

		if not matched_cache:
			data = self.data
			result = self.empty_result.items()

			if match_robots(data, result):
				result_dict = dict(result)
			else:
				match_os(data, result)
				browser_match, browser_version = match_browser(data, result)

				result_dict = dict(result)

				if browser_match:
					result_dict['ua_name'] = '%s %s' % (result_dict['ua_family'], browser_version)

		add_to_cache(result_dict, matched_cache)

		return result_dict

	def _parseIniFile(self, file_content):
		"""
		Parse an ini file into a dictionary structure
		"""

		def toPythonReg(reg):
			reg_l = reg[1:reg.rfind('/')]
			reg_r = reg[reg.rfind('/')+1:]
			flag = 0
			if 's' in reg_r: flag = flag | re.S
			if 'i' in reg_r: flag = flag | re.I

			return re.compile(reg_l,flag)

		def read_ini_file(file_content):
			data = {}

			current_section = ''
			section_pat = re.compile(r'^\[(\S+)\]$')
			option_pat = re.compile(r'^(\d+)\[\]\s=\s"(.*)"$')

			for line in file_content.split("\n"):
				option = option_pat.findall(line)
				if option:
					key = int(option[0][0])
					val = option[0][1].decode('utf-8')

					if data[current_section].has_key(key):
						data[current_section][key].append(val)
					else:
						data[current_section][key] = [val,]
				else:
					section = section_pat.findall(line)
					if section:
						current_section = section[0]
						data[current_section] = OrderedDict()

			return data

		def get_matching_object(reg_list, details, details_template, browser_types=None, browser_os=None, os=None):
			m_data = []
			m_details = {}

			for k, r_obj in reg_list.iteritems():
				reg = toPythonReg(r_obj[0])
				m_id = int(r_obj[1])

				obj = {'re': reg, 'details_key': m_id}
				m_data.append(obj)

			for m_id, details in details.iteritems():
				obj = []

				# OS details from browser
				if browser_os and os and m_id in browser_os:
					key = int(browser_os[m_id][0])
					if key in os['details']:
						obj.extend(os['details'][key])

				for i, det in enumerate(details):
					if details_template[i] == 'ua_info_url':
						det = self.info_url + det

					if browser_types and details_template[i] == 'typ':
						det = browser_types[int(det)][0]

					obj.append((details_template[i], det))

				m_details[m_id] = obj

			return {
					'reg': m_data,
					'details': m_details,
				}

		def get_robots_object(robots, os_details, browser_template, os_template):
			r_data = []
			for r_id, robot in robots.iteritems():
				obj = {}

				re = robot[0]
				details_browser = robot[1:7] + robot[8:]
				details_os = os_details[robot[7]] if robot[7] else []

				obj['ua'] = re
				obj['details'] = [('typ', 'Robot'),]

				for i, name in enumerate(browser_template):
					det = details_browser[i] if len(details_browser) > i else self.empty_result[name]

					if name == 'ua_info_url':
						det = self.info_url + det

					obj['details'].append((name, det))

				for i, name in enumerate(os_template):
					det = details_os[i] if len(details_os) > i else self.empty_result[name]
					obj['details'].append((name, det))

				r_data.append(obj)

			return r_data


		os_template = ['os_family', 'os_name', 'os_url', 'os_company', 'os_company_url', 'os_icon']
		browser_template = ['typ', 'ua_family', 'ua_url', 'ua_company', 'ua_company_url', 'ua_icon', 'ua_info_url']
		robot_template = ['ua_family', 'ua_name', 'ua_url', 'ua_company', 'ua_company_url', 'ua_icon', 'ua_info_url']

		data = read_ini_file(file_content)

		robots = get_robots_object(data['robots'], data['os'], robot_template, os_template)
		os = get_matching_object(data['os_reg'], data['os'], os_template)
		browser = get_matching_object(data['browser_reg'], data['browser'], browser_template, data['browser_type'], data['browser_os'], os)

		return {
			'robots': robots,
			'os': os,
			'browser': browser,
		}

	def _fetchURL(self, url):
		"""
		Get remote context by a given url
		"""
		resq = urllib2.Request(url)
		context = urllib2.urlopen(resq)
		return context.read()

	def _checkCache(self):
		"""
		check whether the cache available or not?
		"""
		cache_file = self.cache_file_name
		if not os.path.exists(cache_file):
			return False

		return True

	def updateData(self):
		"""
		Check whether data is out-of-date
		"""

		try:
			cache_file = open(self.cache_file_name,'wb')
			ini_file = self._fetchURL(self.ini_url)
			ini_data = self._parseIniFile(ini_file)
		except:
			raise UASException("Failed to download cache data")

		self.data = ini_data
		pickle.dump(ini_data, cache_file)

		return True

	def loadData(self):
		"""
		start to load cache data
		"""
		if self._checkCache():
			self.data = pickle.load(open(self.cache_file_name,'rb'))
		else:
			self.updateData()
