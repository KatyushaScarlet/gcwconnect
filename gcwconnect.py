#!/usr/bin/env python

#	gcwconnect.py
#
#	Requires: pygame, urllib, json
#
#	Copyright (c) 2013-2020 Hans Kokx
#
#	Licensed under the GNU General Public License, Version 3.0 (the "License");
#	you may not use this file except in compliance with the License.
#	You may obtain a copy of the License at
#
#	http://www.gnu.org/copyleft/gpl.html
#
#	Unless required by applicable law or agreed to in writing, software
#	distributed under the License is distributed on an "AS IS" BASIS,
#	WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#	See the License for the specific language governing permissions and
#	limitations under the License.


'''

TODO:
* Add option to cancel connecting to a network
* Clean up host ap info display. It's ugly.

'''


import subprocess as SU
import sys, time, os, shutil
import pygame
from pygame.locals import *
import pygame.gfxdraw
from os import listdir
from urllib import parse
import json

# What is our wireless interface?
wlan = "wlan0"

## That's it for options. Everything else below shouldn't be edited.
confdir = os.environ['HOME'] + "/.local/share/gcwconnect/"
netconfdir = confdir+"networks/"
sysconfdir = "/usr/local/etc/network/"
datadir = "/usr/share/gcwconnect/"
if not os.path.exists(datadir):
	datadir = "data/"

surface = pygame.display.set_mode((320,240))
selected_key = ''
passphrase = ''
active_menu = ''
encryptiontypes = ("WEP-40","WEP-128","WPA", "WPA2")
encryptionLabels = ('None', 'WEP', 'WPA', 'WPA2')
colors = {
		"darkbg": (41, 41, 41),
		"lightbg": (84, 84, 84),
		"activeselbg": (160, 24, 24),
		"inactiveselbg": (84, 84, 84),
		"activetext": (255, 255, 255),
		"inactivetext": (128, 128, 128),
		"lightgrey": (200,200,200),
		'logogcw': (255, 255, 255),
		'logoconnect': (216, 32, 32),
		"color": (255,255,255),
		"yellow": (128, 128, 0),
		"blue": (0, 0, 128),
		"red": (128, 0, 0),
		"green": (0, 128, 0),
		"black": (0, 0, 0),
		"white": (255, 255, 255),
		}

mac_addresses = {}


## Initialize the display, for pygame
if not pygame.display.get_init():
	pygame.display.init()
if not pygame.font.get_init():
	pygame.font.init()

surface.fill(colors["darkbg"])
pygame.mouse.set_visible(False)
pygame.key.set_repeat(199,69) #(delay,interval)

## Fonts
font_path   = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
font_tiny   = pygame.font.Font(font_path, 8)
font_small  = pygame.font.Font(font_path, 10)
font_medium = pygame.font.Font(font_path, 12)
font_large  = pygame.font.Font(font_path, 16)
font_huge   = pygame.font.Font(font_path, 48)
gcw_font        = pygame.font.Font(os.path.join(datadir, 'gcwzero.ttf'), 25)
font_mono_small = pygame.font.Font(os.path.join(datadir, 'Inconsolata.otf'), 11)

## File management
def createPaths(): # Create paths, if necessary
	if not os.path.exists(confdir):
		os.makedirs(confdir)
	if not os.path.exists(netconfdir):
		os.makedirs(netconfdir)
	if not os.path.exists(sysconfdir):
		os.makedirs(sysconfdir)

## Interface management
def ifDown(): # Disconnect from wifi / bring down the hosted AP
	SU.Popen(['sudo', '/usr/sbin/ifdown', wlan], close_fds=True).wait()
	SU.Popen(['sudo', '/usr/sbin/ap', '--stop'], close_fds=True).wait()

def ifUp(): # Try to connect the wlan interface to wifi
	SU.Popen(['sudo', '/usr/sbin/ifup', wlan], close_fds=True).wait() == 0
	status = checkInterfaceStatus()
	return status

def enableIface(): # Enables the wlan interface. Returns False if the interface was previously enabled
	check = checkInterfaceStatus()
	if check is not False:
		return False

	modal("Enabling WiFi...")
	drawInterfaceStatus()
	pygame.display.update()

	while True:
		if SU.Popen(['sudo', '/usr/sbin/ip', 'link', 'set', wlan, 'up'], close_fds=True).wait() == 0:
			break
		time.sleep(0.1);

	return True

def disableIface(): # Disables the wlan interface
	SU.Popen(['sudo', '/usr/sbin/ip', 'link', 'set', wlan, 'down'], close_fds=True).wait()

def getIp(): # Returns the current IP address of the wlan interface
	ip = None
	with open(os.devnull, "w") as fnull:
		output = SU.Popen(['/usr/sbin/ip', '-4', 'a', 'show', wlan],
				stderr=fnull, stdout=SU.PIPE, close_fds=True).stdout.readlines()
	
	for line in output:
		if line.decode("utf-8").strip().startswith("inet"):
			ip = line.decode("utf-8").split()[1].split("/")[0]
	
	return ip

def getMacAddress(): # Returns the wlan MAC address, or False if the interface is disabled
	try:
		with open("/sys/class/net/" + wlan + "/address", "rb") as mac_file:
			return mac_file.readline(17)
	except IOError:
		return False  # WiFi is disabled

def getCurrentSSID():  # What network are we connected to?
	ssid = None
	with open(os.devnull, "w") as fnull:
		output = SU.Popen(['/usr/sbin/iw', 'dev', wlan, 'link'],
				stdout=SU.PIPE, stderr=fnull, close_fds=True).stdout.readlines()
	if output is not None:
		for line in output:
			if line.decode("utf-8").strip().startswith('SSID'):
				ssid = line.decode("utf-8").split()[1]

	return ssid

def getSavedNetworkKey(ssid):  # What's the key for a given saved network?
	key = None
	conf = netconfdir + parse.quote_plus(ssid) + ".conf"
	output = open(conf, "r")
	if output is not None:
		for line in output:
			if line.strip().startswith('WLAN_PASSPHRASE'):
				key = str(line.strip().split("=")[1])[1:-1]

	return key


def checkIfInterfaceIsDormant(): # Returns True/False depending on whether interface is dormant
	operstate = False
	try:
		with open("/sys/class/net/" + wlan + "/dormant", "rb") as state:
			return state.readline().decode("utf-8").strip()
	except IOError:
		return False  # WiFi is disabled

def checkInterfaceStatus():  # Returns a str() containing the interface status; False if interface is down
	interface_status = False

	interface_is_up = checkIfInterfaceIsDormant()
	connected_to_network = getCurrentSSID()
	ip_address = getIp()

	if interface_is_up != False:
		interface_status = "Up"
		if connected_to_network is not None:
			interface_status = "Associated"
			if ip_address is not None:
				interface_status = "Connected"
	return interface_status

def connectToAp(ssid): # Connect to network (ssid)
	saved_file = netconfdir + parse.quote_plus(ssid) + ".conf"
	if os.path.exists(saved_file):
		shutil.copy2(saved_file, sysconfdir+"config-"+wlan+".conf")

	iface_status = checkInterfaceStatus()
	if iface_status == True:
		disconnectFromAp()
	else:
		enableIface()

	modal("Connecting...")
	ifUp()
	
	connected_to_network = getCurrentSSID()
	if connected_to_network != None:
		modal('Connected!', timeout=True)
	else:
		modal('Connection failed!', timeout=True)

	pygame.display.update()
	drawStatusBar()
	drawInterfaceStatus()
	return True

def disconnectFromAp(): # Disconnect from the currently associated access point
	modal("Disconnecting...")
	ifDown()
	
	pygame.display.update()
	drawStatusBar()
	drawInterfaceStatus()

def scanForNetworks(): # Returns a list of networks in range
	wasnotenabled = enableIface()
	modal("Scanning...")

	with open(os.devnull, "w") as fnull:
		output = SU.Popen(['sudo', '/usr/sbin/wlan-scan', wlan],
				stdout=SU.PIPE, stderr=fnull, close_fds=True, encoding="utf-8").stdout.readlines()

	aps = []

	for item in output:
		if len(item) > 2:
			try:
				item = item.strip()
				if item[-1] == ',':
					item = item[0:-1]
				
				if len(json.loads(item)['ssid'].strip()) != 0: #FIXME: for now, we're going to ignore hidden networks
					aps.append(json.loads(item))
			except:
				pass
		else:
			pass

	final = sorted(aps, key=lambda x: x['quality'], reverse=True) # sort by quality
	redraw()

	# if wasnotenabled:
		# disableIface()
	return final

## Draw interface elements
class hint:
	global colors
	def __init__(self, button, text, x, y, bg=colors["darkbg"]):
		self.button = button
		self.text = text
		self.x = x
		self.y = y
		self.bg = bg
		self.drawhint()

	def drawhint(self):
		if self.button == 'l' or self.button == 'r':
			if self.button == 'l':
				aaFilledCircle(surface, colors["black"], (self.x, self.y+5), 5)
				pygame.draw.rect(surface, colors["black"], (self.x-5, self.y+6, 10, 5))


			if self.button == 'r':
				aaFilledCircle(surface, colors["black"], (self.x+15, self.y+5), 5)
				pygame.draw.rect(surface, colors["black"], (self.x+11, self.y+6, 10, 5))

			button = pygame.draw.rect(surface, colors["black"], (self.x, self.y, 15, 11))
			text = font_tiny.render(self.button.upper(), True, colors["white"], colors["black"])
			buttontext = text.get_rect()
			buttontext.center = button.center
			surface.blit(text, buttontext)

		if self.button == "select" or self.button == "start":
			lbox = aaFilledCircle(surface, colors["black"], (self.x+5, self.y+5), 6)
			rbox = aaFilledCircle(surface, colors["black"], (self.x+29, self.y+5), 6)
			straightbox = lbox.union(rbox)
			buttoncenter = straightbox.center
			if self.button == 'select':
				straightbox.y = lbox.center[1]
			straightbox.height = int(round((straightbox.height + 1) / 2))
			pygame.draw.rect(surface, colors["black"], straightbox)

			roundedbox = Rect(lbox.midtop, (rbox.midtop[0] - lbox.midtop[0], lbox.height - straightbox.height))
			if self.button == 'start':
				roundedbox.bottomleft = lbox.midbottom
			pygame.draw.rect(surface, colors["black"], roundedbox)
			text = font_tiny.render(self.button.upper(), True, colors["white"], colors["black"])
			buttontext = text.get_rect()
			buttontext.center = buttoncenter
			buttontext.move_ip(0, 1)
			surface.blit(text, buttontext)

			labelblock = pygame.draw.rect(surface, self.bg, (self.x+40,self.y,25,14))
			labeltext = font_tiny.render(self.text, True, colors["white"], self.bg)
			surface.blit(labeltext, labelblock)

		elif self.button in ('a', 'b', 'x', 'y'):
			if self.button == "a":
				color = colors["green"]
			elif self.button == "b":
				color = colors["blue"]
			elif self.button == "x":
				color = colors["red"]
			elif self.button == "y":
				color = colors["yellow"]

			labelblock = pygame.draw.rect(surface, self.bg, (self.x+10,self.y,35,14))
			labeltext = font_tiny.render(self.text, True, colors["white"], self.bg)
			surface.blit(labeltext, labelblock)

			button = aaFilledCircle(surface, color, (self.x,self.y+5), 6) # (x, y)
			text = font_tiny.render(self.button.upper(), True, colors["white"], color)
			buttontext = text.get_rect()
			buttontext.center = button.center
			surface.blit(text, buttontext)

		elif self.button in ('left', 'right', 'up', 'down'):

			# Vertical
			pygame.draw.rect(surface, colors["black"], (self.x+5, self.y-1, 4, 12))
			pygame.draw.rect(surface, colors["black"], (self.x+6, self.y-2, 2, 14))

			# Horizontal
			pygame.draw.rect(surface, colors["black"], (self.x+1, self.y+3, 12, 4))
			pygame.draw.rect(surface, colors["black"], (self.x, self.y+4, 14, 2))

			if self.button == "left":
				pygame.draw.rect(surface, colors["white"], (self.x+2, self.y+4, 3, 2))
			elif self.button == "right":
				pygame.draw.rect(surface, colors["white"], (self.x+9, self.y+4, 3, 2))
			elif self.button == "up":
				pygame.draw.rect(surface, colors["white"], (self.x+6, self.y+1, 2, 3))
			elif self.button == "down":
				pygame.draw.rect(surface, colors["white"], (self.x+6, self.y+7, 2, 3))

			labelblock = pygame.draw.rect(surface, self.bg, (self.x+20,self.y,35,14))
			labeltext = font_tiny.render(self.text, True, (255, 255, 255), self.bg)
			surface.blit(labeltext, labelblock)

class LogoBar(object):
	'''The logo area at the top of the screen.'''

	def __init__(self):
		self.text1 = gcw_font.render('GCW', True, colors['logogcw'], colors['lightbg'])
		self.text2 = gcw_font.render('CONNECT', True, colors['logoconnect'], colors['lightbg'])

	def draw(self):
		pygame.draw.rect(surface, colors['lightbg'], (0,0,320,34))
		pygame.draw.line(surface, colors['white'], (0, 34), (320, 34))

		rect1 = self.text1.get_rect()
		rect1.topleft = (8 + 5 + 1, 5)
		surface.blit(self.text1, rect1)

		rect2 = self.text2.get_rect()
		rect2.topleft = rect1.topright
		surface.blit(self.text2, rect2)

def drawStatusBar():  # Set up the status bar
	connected_to_network = getCurrentSSID()
	if connected_to_network is None:
		connected_to_network = "Not connected"
	global colors
	pygame.draw.rect(surface, colors['lightbg'], (0,224,320,16))
	pygame.draw.line(surface, colors['white'], (0, 223), (320, 223))
	wlantext = font_mono_small.render(connected_to_network, True, colors['white'], colors['lightbg'])
	wlan_text = wlantext.get_rect()
	wlan_text.topleft = (2, 225)
	surface.blit(wlantext, wlan_text)

def drawInterfaceStatus(): # Interface status badge
	global colors
	wlanstatus = checkInterfaceStatus()
	if not wlanstatus:
		wlanstatus = wlan+" is off."
	else:
		wlanstatus = getCurrentSSID()

	wlantext = font_mono_small.render(wlanstatus, True, colors['white'], colors['lightbg'])
	wlan_text = wlantext.get_rect()
	wlan_text.topleft = (2, 225)
	surface.blit(wlantext, wlan_text)

	# Note that the leading space here is intentional, to more cleanly overdraw any overly-long
	# strings written to the screen beneath it (i.e. a very long ESSID)
	if checkInterfaceStatus():
		ip_address = getIp()
		if ip_address is None:
			ip_address = ''
		text = font_mono_small.render(" "+ip_address, True, colors['white'], colors['lightbg'])
		interfacestatus_text = text.get_rect()
		interfacestatus_text.topright = (317, 225)
		surface.blit(text, interfacestatus_text)
	else:
		mac = mac_addresses.get(wlan)  #FIXME: grabbed by enableiface()
		if mac is not None:
			text = font_mono_small.render(" "+mac.decode("utf-8"), True, colors['white'], colors['lightbg'])
			interfacestatus_text = text.get_rect()
			interfacestatus_text.topright = (317, 225)
			surface.blit(text, interfacestatus_text)

def redraw():
	global colors
	surface.fill(colors['darkbg'])
	logoBar.draw()
	mainMenu()
	if wirelessmenu is not None:
		wirelessmenu.draw()
		pygame.draw.rect(surface, colors['darkbg'], (0, 208, 320, 16))
		hint("select", "Edit", 4, 210)
		hint("a", "Connect", 75, 210)
		hint("b", "/", 130, 210)
		hint("left", "Back", 145, 210)
	if active_menu == "main":
		pygame.draw.rect(surface, colors['darkbg'], (0, 208, 320, 16))
		hint("a", "Select", 8, 210)
	if active_menu == "saved":
		hint("y", "Forget", 195, 210)

	drawStatusBar()
	drawInterfaceStatus()
	pygame.display.update()


## Connect to a network
def writeConfigToDisk(ssid): # Write wireless configuration to disk
	global passphrase

	if passphrase:
		if passphrase == "none":
			passphrase = ""

	conf = netconfdir + parse.quote_plus(ssid) + ".conf"

	f = open(conf, "w")
	f.write('WLAN_ESSID="'+ssid+'"\n')
	f.write('WLAN_PASSPHRASE="'+passphrase+'"\n')
	f.write('WLAN_ENCRYPTION="wpa2"\n') # Default to WPA2, because it's 2020.
	f.close()

## HostAP
def startap():
	global wlan
	if checkInterfaceStatus():
		disconnectFromAp()

	modal("Creating AP...")
	if SU.Popen(['sudo', '/usr/sbin/ap', '--start'], close_fds=True).wait() == 0:
		modal('AP created!', timeout=True)
	else:
		modal('Failed to create AP...', wait=True)
	redraw()
	return True

## Input methods

keyLayouts = {
	'qwertyNormal': (
			('`', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '='),
			('q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', '[', ']', '\\'),
			('a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';', '\''),
			('z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/'),
			),
	'qwertyShift': (
			('~', '!', '@', '#', '$', '%', '^', '&', '*', '(', ')', '_', '+'),
			('Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', '{', '}', '|'),
			('A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ':', '"'),
			('Z', 'X', 'C', 'V', 'B', 'N', 'M', '<', '>', '?'),
			)
	}
keyboardCycleOrder = ('qwertyNormal', 'qwertyShift')
def nextKeyboard(board):
	return keyboardCycleOrder[
			(keyboardCycleOrder.index(board) + 1) % len(keyboardCycleOrder)
			]

class key:
	global colors
	def __init__(self):
		self.key = []
		self.selection_color = colors['activeselbg']
		self.text_color = colors['activetext']
		self.selection_position = (0,0)
		self.selected_item = 0

	def init(self, key, row, column):
		self.key = key
		self.row = row
		self.column = column
		self.drawkey()

	def drawkey(self):
		key_width = 16
		key_height = 16

		top = 136 + self.row * 20
		left = 32 + self.column * 20

		if len(self.key) > 1:
			key_width = 36
		keybox = pygame.draw.rect(surface, colors['lightbg'], (left,top,key_width,key_height))
		text = font_medium.render(self.key, True, colors['white'], colors['lightbg'])
		label = text.get_rect()
		label.center = keybox.center
		label.y -= 1
		surface.blit(text, label)

class radio:
	global colors
	def __init__(self):
		self.key = []
		self.selection_color = colors['activeselbg']
		self.text_color = colors['activetext']
		self.selection_position = (0,0)
		self.selected_item = 0

	def init(self, key, row, column):
		self.key = key
		self.row = row
		self.column = column
		self.drawkey()

	def drawkey(self):
		key_width = 64
		key_height = 16

		top = 136 + self.row * 20
		left = 32 + self.column * 64

		if len(self.key) > 1:
			key_width = 64
		radiobutton = aaFilledCircle(surface, colors['white'], (left, top), 8)
		aaFilledCircle(surface, colors['darkbg'], (left, top), 6)
		text = font_medium.render(self.key, True, (255, 255, 255), colors['darkbg'])
		label = text.get_rect()
		label.left = radiobutton.right + 8
		label.top = radiobutton.top + 4
		surface.blit(text, label)

def aaFilledCircle(surface, color, center, radius): # Draws a filled circle
	'''Helper function to draw anti-aliased circles using an interface similar
	to pygame.draw.circle.
	'''
	x, y = center
	pygame.gfxdraw.aacircle(surface, x, y, radius, color)
	pygame.gfxdraw.filled_circle(surface, x, y, radius, color)
	return Rect(x - radius, y - radius, radius * 2 + 1, radius * 2 + 1)

def modal(text, wait=False, timeout=False, query=False):
	global colors
	dialog = pygame.draw.rect(surface, colors['lightbg'], (64,88,192,72))
	pygame.draw.rect(surface, colors['white'], (62,86,194,74), 2)

	text = font_medium.render(text, True, colors['white'], colors['lightbg'])
	modal_text = text.get_rect()
	modal_text.center = dialog.center

	surface.blit(text, modal_text)
	pygame.display.update()

	if wait:
		abutton = hint("a", "Continue", 205, 145, colors['lightbg'])
		pygame.display.update()
	elif timeout:
		time.sleep(2.5)
		redraw()
	elif query:
		abutton = hint("a", "Confirm", 150, 145, colors['lightbg'])
		bbutton = hint("b", "Cancel", 205, 145, colors['lightbg'])
		pygame.display.update()
		while True:
			for event in pygame.event.get():
				if event.type == KEYDOWN:
					if event.key == K_LCTRL:
						return True
					elif event.key == K_LALT:
						return

	if not wait:
		return

	while True:
		for event in pygame.event.get():
			if event.type == KEYDOWN and event.key == K_LCTRL:
				redraw()
				return

def getSSID():
	global passphrase
	displayinputlabel("ssid")
	drawKeyboard("qwertyNormal")
	getSoftKeyInput("qwertyNormal", "ssid")
	ssid = passphrase
	passphrase = ''
	return ssid

def drawKeyboard(board):
	global colors

	# Draw keyboard background
	pygame.draw.rect(surface, colors['darkbg'], (0,134,320,106))

	# Draw bottom background
	pygame.draw.rect(surface, colors['lightbg'], (0,224,320,16))
	pygame.draw.line(surface, colors['white'], (0, 223), (320, 223))

	hint("select", "Cancel", 4, 227, colors['lightbg'])
	hint("start", "Finish", 75, 227, colors['lightbg'])
	hint("x", "Delete", 155, 227, colors['lightbg'])
	hint("y", "Shift", 200, 227, colors['lightbg'])

	hint("a", "Enter", 285, 227, colors['lightbg'])

	# Draw the keys
	z = key()
	for row, rowData in enumerate(keyLayouts[board]):
		for column, label in enumerate(rowData):
			z.init(label, row, column)

	pygame.display.update()

def getSoftKeyInput(board, kind, ssid=""):
	selectkey(board, kind)
	return softKeyInput(board, kind, ssid)

def softKeyInput(keyboard, kind, ssid):
	global passphrase
	global encryption
	global securitykey
	def update():
		displayinputlabel("key")

	while True:
		event = pygame.event.wait()

		if event.type == KEYDOWN:
			if event.key == K_RETURN:		# finish input
				selectkey(keyboard, kind, "enter")
				redraw()
				if ssid == '':
					return False
				writeConfigToDisk(ssid)
				connectToAp(ssid)
				return True

			if event.key == K_UP:		# Move cursor up
				selectkey(keyboard, kind, "up")
			if event.key == K_DOWN:		# Move cursor down
				selectkey(keyboard, kind, "down")
			if event.key == K_LEFT:		# Move cursor left
				selectkey(keyboard, kind, "left")
			if event.key == K_RIGHT:	# Move cursor right
				selectkey(keyboard, kind, "right")
			if event.key == K_LCTRL:	# A button
				selectkey(keyboard, kind, "select")
			if event.key == K_LALT:		# B button
				selectkey(keyboard, kind, "space")
			if event.key == K_SPACE:	# Y button (swap keyboards)
				keyboard = nextKeyboard(keyboard)
				drawKeyboard(keyboard)
				selectkey(keyboard, kind, "swap")
			if event.key == K_LSHIFT:	# X button
				selectkey(keyboard, kind, "delete")
			if event.key == K_ESCAPE:	# Select key
				passphrase = ''

				try:
					securitykey
				except NameError:
					pass
				else:
					del securitykey
				redraw()
				return False

def displayinputlabel(kind, size=24): # Display passphrase on screen
	global colors
	global encryption

	if kind == "ssid":
		pygame.draw.rect(surface, colors['darkbg'], (0,100,320,34))
		labelblock = pygame.draw.rect(surface, colors['white'], (0,35,320,20))
		labeltext = font_large.render("Enter new SSID", True, colors['lightbg'], colors['white'])
		label = labeltext.get_rect()
		label.center = labelblock.center
		surface.blit(labeltext, label)

	elif kind == "key":
		labelblock = pygame.draw.rect(surface, colors['white'], (0,35,320,20))
		labeltext = font_large.render("Enter network key", True, colors['lightbg'], colors['white'])
		label = labeltext.get_rect()
		label.center = labelblock.center
		surface.blit(labeltext, label)
		
		hintblock = pygame.draw.rect(surface, colors['darkbg'], (0, 100, 320, 34))


	# Input area
	bg = pygame.draw.rect(surface, colors['white'], (0, 55, 320, 45))
	text = "[ "
	text += passphrase
	text += " ]"
	pw = font_mono_small.render(text, True, (0, 0, 0), colors['white'])
	pwtext = pw.get_rect()
	pwtext.center = bg.center
	surface.blit(pw, pwtext)
	pygame.display.update()

def selectkey(keyboard, kind, direction=""):
	def highlightkey(keyboard, pos='[0,0]'):
		drawKeyboard(keyboard)
		pygame.display.update()

		left_margin = 32
		top_margin = 136

		if pos[0] > left_margin:
			x = left_margin + (16 * (pos[0]))
		else:
			x = left_margin + (16 * pos[0]) + (pos[0] * 4)


		if pos[1] > top_margin:
			y = top_margin + (16 * (pos[1]))
		else:
			y = top_margin + (16 * pos[1]) + (pos[1] * 4)

		pointlist = [
				(x, y),
				(x + 16, y),
				(x + 16, y + 16),
				(x, y + 16),
				(x, y)
				]
		lines = pygame.draw.lines(surface, (255,255,255), True, pointlist, 1)
		pygame.display.update()

	global selected_key
	global passphrase

	if not selected_key:
		selected_key = [0,0]

	def clampRow():
		selected_key[1] = min(selected_key[1], len(layout) - 1)
	def clampColumn():
		selected_key[0] = min(selected_key[0], len(layout[selected_key[1]]) - 1)

	layout = keyLayouts[keyboard]
	if direction == "swap":
		# Clamp row first since each row can have a different number of columns.
		clampRow()
		clampColumn()
	elif direction == "up":
		selected_key[1] = (selected_key[1] - 1) % len(layout)
		clampColumn()
	elif direction == "down":
		selected_key[1] = (selected_key[1] + 1) % len(layout)
		clampColumn()
	elif direction == "left":
		selected_key[0] = (selected_key[0] - 1) % len(layout[selected_key[1]])
	elif direction == "right":
		selected_key[0] = (selected_key[0] + 1) % len(layout[selected_key[1]])
	elif direction == "select":
		passphrase += layout[selected_key[1]][selected_key[0]]
		if len(passphrase) > 20:
			logoBar.draw()
			displayinputlabel(kind, 12)
		else:
			displayinputlabel(kind)
	elif direction == "space":
		passphrase += ' '
		if len(passphrase) > 20:
			logoBar.draw()
			displayinputlabel(kind, 12)
		else:
			displayinputlabel(kind)
	elif direction == "delete":
		if len(passphrase) > 0:
			passphrase = passphrase[:-1]
			logoBar.draw()
			if len(passphrase) > 20:
				displayinputlabel(kind, 12)
			else:
				displayinputlabel(kind)

	highlightkey(keyboard, selected_key)

class Menu:
	font = font_medium
	dest_surface = surface
	canvas_color = colors["darkbg"]

	elements = []

	def __init__(self):
		self.set_elements([])
		self.selected_item = 0
		self.origin = (0,0)
		self.menu_width = 0
		self.menu_height = 0
		self.selection_color = colors["activeselbg"]
		self.text_color = colors["activetext"]
		self.font = font_medium

	def move_menu(self, top, left):
		self.origin = (top, left)

	def set_colors(self, text, selection, background):
		self.text_color = text
		self.selection_color = selection

	def set_elements(self, elements):
		self.elements = elements

	def get_position(self):
		return self.selected_item

	def get_selected(self):
		return self.elements[self.selected_item]

	def init(self, elements, dest_surface):
		self.set_elements(elements)
		self.dest_surface = dest_surface

	def draw(self,move=0):
		# Clear any old text (like from apinfo()), but don't overwrite button hint area above statusbar
		pygame.draw.rect(surface, colors['darkbg'], (0,35,320,173))

		if len(self.elements) == 0:
			return

		self.selected_item = (self.selected_item  + move) % len(self.elements)

		# Which items are to be shown?
		if self.selected_item <= 2: # We're at the top
			visible_elements = self.elements[0:6]
			selected_within_visible = self.selected_item
		elif self.selected_item >= len(self.elements) - 3: # We're at the bottom
			visible_elements = self.elements[-6:]
			selected_within_visible = self.selected_item - (len(self.elements) - len(visible_elements))
		else: # The list is larger than 5 elements, and we're in the middle
			visible_elements = self.elements[self.selected_item - 2:self.selected_item + 3]
			selected_within_visible = 2

		# What width does everything have?
		max_width = max([self.get_item_width(visible_element) for visible_element in visible_elements])
		# And now the height
		heights = [self.get_item_height(visible_element) for visible_element in visible_elements]
		total_height = sum(heights)

		# Background
		menu_surface = pygame.Surface((max_width, total_height))
		menu_surface.fill(self.canvas_color)

		# Selection
		left = 0
		top = sum(heights[0:selected_within_visible])
		width = max_width
		height = heights[selected_within_visible]
		selection_rect = (left, top, width, height)
		pygame.draw.rect(menu_surface,self.selection_color,selection_rect)

		# Clear any error elements
		error_rect = (left+width+8, 35, 192, 172)
		pygame.draw.rect(surface,colors['darkbg'],error_rect)

		# Elements
		top = 0
		for i in range(len(visible_elements)):
			self.render_element(menu_surface, visible_elements[i], 0, top)
			top += heights[i]
		self.dest_surface.blit(menu_surface,self.origin)
		return self.selected_item

	def get_item_height(self, element):
		render = self.font.render(element, 1, self.text_color)
		spacing = 5
		return render.get_rect().height + spacing * 2

	def get_item_width(self, element):
		render = self.font.render(element, 1, self.text_color)
		spacing = 5
		return render.get_rect().width + spacing * 2

	def render_element(self, menu_surface, element, left, top):
		render = self.font.render(element, 1, self.text_color)
		spacing = 5
		menu_surface.blit(render, (int(round(left + spacing)), int(round(top + spacing)), render.get_rect().width, render.get_rect().height))

class NetworksMenu(Menu):
	def set_elements(self, elements):
		self.elements = elements

	def get_item_width(self, element):
		the_ssid = element[0]
		render = self.font.render(the_ssid, 1, self.text_color)
		spacing = 15
		return render.get_rect().width + spacing * 2

	def get_item_height(self, element):
		render = self.font.render(element[0], 1, self.text_color)
		spacing = 6
		return (render.get_rect().height + spacing * 2) + 5

	def render_element(self, menu_surface, element, left, top):
		the_ssid = element[0]
		## Wifi signal icons
		percent = element[1]

		try:
			if percent >= 6 and percent <= 24:
				signal_icon = 'wifi-0.png'
			elif percent >= 25 and percent <= 49:
				signal_icon = 'wifi-1.png'
			elif percent >= 50 and percent <= 74:
				signal_icon = 'wifi-2.png'
			elif percent >= 75:
				signal_icon = 'wifi-3.png'
			else:
				signal_icon = 'transparent.png'
		except:
			signal_icon = 'transparent.png'
			percent = None

		qual_img = pygame.image.load((os.path.join(datadir, signal_icon))).convert_alpha()
		# enc_img = pygame.image.load((os.path.join(datadir, enc_icon))).convert_alpha()

		ssid = font_mono_small.render(the_ssid, 1, self.text_color)
		if type(percent) == int:
			strength = font_small.render(str(str(percent) + "%").rjust(4), 1, colors["lightgrey"])
		spacing = 2

		menu_surface.blit(ssid, (int(round(left + spacing)), int(round(top))))
		# menu_surface.blit(enc, (int(round(left + enc_img.get_rect().width + 12)), int(round(top + 18))))
		# menu_surface.blit(enc_img, (int(round(left + 8)), int(round((top + 24) -
							# (enc_img.get_rect().height / 2)))))
		if type(percent) == int:
			menu_surface.blit(strength, (left + 137, top + 18, strength.get_rect().width, strength.get_rect().height))
		qual_x = left + 200 - qual_img.get_rect().width - 3
		qual_y = top + 7 + 6 
		qual_y = top + 7 + 6 
		qual_y = top + 7 + 6 
		menu_surface.blit(qual_img, (qual_x, qual_y))
		pygame.display.update()

	def draw(self,move=0):
		if len(self.elements) == 0:
			return

		if move != 0:
			self.selected_item += move
			if self.selected_item < 0:
				self.selected_item = 0
			elif self.selected_item >= len(self.elements):
				self.selected_item = len(self.elements) - 1

		# Which items are to be shown?
		if self.selected_item <= 2: # We're at the top
			visible_elements = self.elements[0:5]
			selected_within_visible = self.selected_item
		elif self.selected_item >= len(self.elements) - 3: # We're at the bottom
			visible_elements = self.elements[-5:]
			selected_within_visible = self.selected_item - (len(self.elements) - len(visible_elements))
		else: # The list is larger than 5 elements, and we're in the middle
			visible_elements = self.elements[self.selected_item - 2:self.selected_item + 3]
			selected_within_visible = 2

		max_width = 320 - self.origin[0] - 3

		# And now the height
		heights = [self.get_item_height(visible_element) for visible_element in visible_elements]
		total_height = sum(heights)

		# Background
		menu_surface = pygame.Surface((max_width, total_height))
		menu_surface.fill(self.canvas_color)

		# Selection
		left = 0
		top = sum(heights[0:selected_within_visible])
		width = max_width
		height = heights[selected_within_visible]
		selection_rect = (left, top, width, height)
		pygame.draw.rect(menu_surface,self.selection_color,selection_rect)

		# Elements
		top = 0
		for i in range(len(visible_elements)):
			self.render_element(menu_surface, visible_elements[i], 0, top)
			top += heights[i]
		self.dest_surface.blit(menu_surface,self.origin)
		return self.selected_item

def navigateToMenu(new_menu):
	global colors
	if new_menu == "main":
		menu.set_colors(colors['activetext'], colors['activeselbg'], colors['darkbg'])
		if wirelessmenu is not None:
			wirelessmenu.set_colors(colors['inactivetext'], colors['inactiveselbg'], colors['darkbg'])
	elif new_menu == "ssid" or new_menu == "saved":
		menu.set_colors(colors['inactivetext'], colors['inactiveselbg'], colors['darkbg'])
		wirelessmenu.set_colors(colors['activetext'], colors['activeselbg'], colors['darkbg'])
	return new_menu

wirelessmenu = None
menu = Menu()
menu.move_menu(3, 41)

def mainMenu():
	global wlan
	elems = ['Quit']

	try:
		ap = getCurrentSSID()
		
		if ap is not None:
			elems = ['AP info'] + elems
	except:
		elems = ['Create AP'] + elems

	elems = ["Saved Networks", 'Scan for APs', "Manual Setup"] + elems

	interface_status = checkInterfaceStatus()
	if interface_status == "Connected":
		elems = ['Disconnect'] + elems

	menu.init(elems, surface)
	menu.draw()

def apInfo():
	global wlan

	try:
		ssid = getCurrentSSID()
		key  = getSavedNetworkKey(ssid)

		if ssid is not None:
			ssidlabel = "SSID"
			renderedssidlabel = font_huge.render(ssidlabel, True, colors["lightbg"], colors["darkbg"])
			ssidlabelelement = renderedssidlabel.get_rect()
			ssidlabelelement.right = 318
			ssidlabelelement.top = 36
			surface.blit(renderedssidlabel, ssidlabelelement)

			renderedssid = font_mono_small.render(ssid, True, colors["white"], colors["darkbg"])
			ssidelement = renderedssid.get_rect()
			ssidelement.right = 315
			ssidelement.top = 98
			surface.blit(renderedssid, ssidelement)

			enclabel = "Key"
			renderedenclabel = font_huge.render(enclabel, True, colors["lightbg"], colors["darkbg"])
			enclabelelement = renderedenclabel.get_rect()
			enclabelelement.right = 314 # Drawn a bit leftwards versus "SSID" text, so both right-align pixel-perfectly
			enclabelelement.top = 116
			surface.blit(renderedenclabel, enclabelelement)

			renderedencp = font_mono_small.render(key, True, colors["white"], colors["darkbg"])
			encpelement = renderedencp.get_rect()
			encpelement.right = 315
			encpelement.top = 182
			surface.blit(renderedencp, encpelement)

			pygame.display.update()
	except:
		text = ":("
		renderedtext = font_huge.render(text, True, colors["lightbg"], colors["darkbg"])
		textelement = renderedtext.get_rect()
		textelement.left = 192
		textelement.top = 98
		surface.blit(renderedtext, textelement)
		pygame.display.update()

def createWirelessMenu():
	global wirelessmenu
	wirelessmenu = NetworksMenu()
	wirelessmenu.move_menu(116,40)

def destroyWirelessMenu():
	global wirelessmenu
	wirelessmenu = None

def getSavedNetworks():
	saved_network = {}
	index = 0
	for confName in sorted(listdir(netconfdir)):
		if not confName.endswith('.conf'):
			continue
		ssid = parse.unquote_plus(confName[:-5])

		detail = {
			'ESSID': ssid,
			'Key': ''
			}
		try:
			with open(netconfdir + confName) as f:
				for line in f:
					key, value = line.split('=', 1)
					key = key.strip()
					value = value.strip()
					if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
						value = value[1:-1]
					if key == 'WLAN_ESSID':
						detail['ESSID'] = value
					elif key == 'WLAN_PASSPHRASE':
						detail['Key'] = value
		except IOError as ex:
			print('Error reading conf:', ex)
			pass
		except ValueError as ex:
			print('Error parsing conf line:', line.strip())
			pass
		else:
			saved_network[index] = detail
			index += 1
	
	return saved_network

def createSavedNetworksMenu():
	saved_networks = getSavedNetworks()
	uniq = saved_networks

	if uniq:
		l = []
		for item in sorted(iter(uniq.keys()), key=lambda x: uniq[x]['ESSID']):
			detail = uniq[item]
			l.append([ detail['ESSID'], detail['Key']])
		createWirelessMenu()
		wirelessmenu.init(l, surface)
		wirelessmenu.draw()
	else:
		text = 'empty'
		renderedtext = font_huge.render(text, True, colors["lightbg"], colors["darkbg"])
		textelement = renderedtext.get_rect()
		textelement.left = 152
		textelement.top = 96
		surface.blit(renderedtext, textelement)
		pygame.display.update()

def convertFileNames():
	"""In the directory containing WiFi network configuration files, removes
	backslashes from file names created by older versions of GCW Connect."""
	try:
		confNames = listdir(netconfdir)
	except IOError as ex:
		print("Failed to list files in '%s': %s", (netconfdir, ex))
	else:
		for confName in confNames:
			if not confName.endswith('.conf'):
				continue
			if '\\' in confName:
				old, new = confName, parse.quote_plus(confName.replace('\\', ''))
				try:
					os.rename(os.path.join(netconfdir, old), os.path.join(netconfdir, new))
				except IOError as ex:
					print("Failed to rename old-style network configuration file '%s' to '%s': %s" % (os.path.join(netconfdir, old), new, ex))

if __name__ == "__main__":
	# Persistent variables
	access_points = {}
	active_menu = "main"

	try:
		createPaths()
	except:
		pass ## Can't create directories. Great for debugging on a pc.
	else:
		convertFileNames()

	logoBar = LogoBar()

	redraw()
	while True:
		time.sleep(0.01)
		for event in pygame.event.get():
			## GCW-Zero keycodes:
			# A = K_LCTRL
			# B = K_LALT
			# X = K_LSHIFT
			# Y = K_SPACE
			# L = K_TAB
			# R = K_BACKSPACE
			# start = K_RETURN
			# select = K_ESCAPE
			# power up = K_KP0
			# power down = K_PAUSE

			if event.type == QUIT:
				pygame.display.quit()
				sys.exit()

			elif event.type == KEYDOWN:
				if event.key == K_PAUSE: 		# Power down
					pass
				elif event.key == K_TAB: 		# Left shoulder button
					pass
				elif event.key == K_BACKSPACE: 	# Right shoulder button
					pass
				elif event.key == K_KP0:		# Power up
					pass
				elif event.key == K_UP: 		# Arrow up the menu
					if active_menu == "main":
						menu.draw(-1)
					elif active_menu == "ssid" or active_menu == "saved":
						wirelessmenu.draw(-1)
				elif event.key == K_DOWN: 		# Arrow down the menu
					if active_menu == "main":
						menu.draw(1)
					elif active_menu == "ssid" or active_menu == "saved":
						wirelessmenu.draw(1)
				elif event.key == K_RIGHT:
					if wirelessmenu is not None and active_menu == "main":
						active_menu = navigateToMenu("ssid")
						redraw()
				elif event.key == K_LALT or event.key == K_LEFT:
					if active_menu == "ssid" or active_menu == "saved":
						destroyWirelessMenu()
						active_menu = navigateToMenu("main")
						try:
							del access_points
						except:
							pass
						redraw()
					elif event.key == K_LALT:
						pygame.display.quit()
						sys.exit()
				elif event.key == K_SPACE:		# Y key pressed
					if active_menu == "saved":
						confirm = modal("Forget AP configuration?", query=True)
						if confirm:
							os.remove(
								netconfdir+parse.quote_plus(str(wirelessmenu.get_selected()[0]))+".conf")
						createSavedNetworksMenu()
						redraw()
						if len(access_points) < 1:
							destroyWirelessMenu()
							active_menu = navigateToMenu("main")
							redraw()
				elif event.key == K_LCTRL or event.key == K_RETURN:	# A key pressed
					## Main menu
					if active_menu == "main":
						if menu.get_selected() == 'Disconnect':
							disconnectFromAp()
							redraw()
						elif menu.get_selected() == 'Scan for APs':
							try:
								access_points = scanForNetworks()
							except: # No access points found
								access_points = {}
								text = ":("
								renderedtext = font_huge.render(text, True, colors["lightbg"], colors["darkbg"])
								textelement = renderedtext.get_rect()
								textelement.left = 192
								textelement.top = 96
								surface.blit(renderedtext, textelement)
								pygame.display.update()

							l = []
							if len(access_points) < 1:
								text = ":("
								renderedtext = font_huge.render(text, True, colors["lightbg"], colors["darkbg"])
								textelement = renderedtext.get_rect()
								textelement.left = 192
								textelement.top = 96
								surface.blit(renderedtext, textelement)
								pygame.display.update()
							else:
								for network in access_points:
									menuitem = [ network['ssid'], network['quality']]
									l.append(menuitem)
								createWirelessMenu()
								wirelessmenu.init(l, surface)
								wirelessmenu.draw()

								active_menu = navigateToMenu("ssid")
								redraw()
						elif menu.get_selected() == 'Manual Setup':
							ssid = ''
							passphrase = ''
							selected_key = ''
							securitykey = ''

							# Get SSID from the user
							ssid = getSSID()
							if ssid == '':
								pass
							else:
								displayinputlabel("key")

								# Get key from the user
								if not encryption == 'None':
									if encryption == "WPA":
										drawKeyboard("qwertyNormal")
										securitykey = getSoftKeyInput("qwertyNormal", "key", ssid)
									elif encryption == "WPA2":
										drawKeyboard("qwertyNormal")
										securitykey = getSoftKeyInput("qwertyNormal", "key", ssid)
									elif encryption == "WEP-40":
										drawKeyboard("wep")
										securitykey = getSoftKeyInput("wep", "key", ssid)
									elif encryption == 'cancel':
										del encryption, ssid, securitykey
										redraw()
								else:
									encryption = "none"
									redraw()
									writeConfigToDisk(ssid)
									connectToAp(ssid)
								try:
									encryption
								except NameError:
									pass

						elif menu.get_selected() == 'Saved Networks':
							createSavedNetworksMenu()
							try:
								active_menu = navigateToMenu("saved")
								redraw()
							except:
								active_menu = navigateToMenu("main")

						elif menu.get_selected() == 'Create AP':
							startap()

						elif menu.get_selected() == 'AP info':
							apInfo()

						elif menu.get_selected() == 'Quit':
							pygame.display.quit()
							sys.exit()

					# SSID menu
					elif active_menu == "ssid":
						ssid = ""
						for network in access_points:
							if network['ssid'].split("-")[0] == "gcwzero":
								ssid = network['ssid']
								conf = netconfdir + parse.quote_plus(ssid) + ".conf"
								passphrase = ssid.split("-")[1]
								connectToAp(ssid)
							else:
								position = int(wirelessmenu.get_position())
								ssid = access_points[position]['ssid']
								conf = netconfdir + parse.quote_plus(ssid) + ".conf"
								if not os.path.exists(conf):
									passphrase = ''
									selected_key = ''
									securitykey = ''
									displayinputlabel("key")
									drawKeyboard("qwertyNormal")
									passphrase = getSoftKeyInput("qwertyNormal", "key", ssid)
								else:
									connectToAp(ssid)
							break

					# Saved Networks menu
					elif active_menu == "saved":
						saved_networks = getSavedNetworks()
						for network in saved_networks:
							position = int(wirelessmenu.get_position())
							ssid = saved_networks[position]['ESSID']
							shutil.copy2(netconfdir + parse.quote_plus(ssid) +
											".conf", sysconfdir+"config-"+wlan+".conf")
							passphrase = saved_networks[position]['Key']
							connectToAp(ssid)
							break

				elif event.key == K_ESCAPE:
					if active_menu == "ssid": # Allow us to edit the existing key
						ssid = ""
						for network in access_points:
							position = int(wirelessmenu.get_position())
							ssid = access_points[position]['ESSID']
							passphrase = ''
							selected_key = ''
							securitykey = ''
							displayinputlabel("key")
							drawKeyboard("qwertyNormal")
							getSoftKeyInput("qwertyNormal", "key", ssid)

					if active_menu == "saved": # Allow us to edit the existing key
						saved_networks = getSavedNetworks()
						position = int(wirelessmenu.get_position())
						ssid = saved_networks[position]['ESSID']
						passphrase = saved_networks[position]['Key']					
						selected_key = ''
						securitykey = ''
						displayinputlabel("key")
						drawKeyboard("qwertyNormal")
						getSoftKeyInput("qwertyNormal", "key", ssid)


		pygame.display.update()
