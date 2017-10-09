#     file: chrm_prof.py
#   author: Jesse Eaton
#  created: 9/27/2017
# modified: 9/30/2017
#  purpose: ChrmProf class. ChrmProf is a chromosome profile and contains a mutated chrm with
#             references to the mutations' original position. Keeps track of copy numbers.

# imports
import sys
import copy
import math
import random

# helpers
def printnow(s):
	s = str(s)
	sys.stdout.write(s)
	sys.stdout.flush()
def printerr(s):
	sys.stderr.write(s)
	sys.stderr.flush()

class ChrmProf:
	# chrm (str) entire chromosome string. ex: "ATCCGA"
	def __init__(self, chrm):
		self.chrm = chrm
		self.org = _OrgNode(0, len(chrm) - 1)
		self.mut = _MutNode(0, len(chrm) - 1)
		self.org.children.append(self.mut)
		self.mut.parent = self.org

	# output: bgns (list of int) [n] beginning positions for each segment
	#         ends (list of int) [n] ending positions for each segment
	#         cps  (list of int) [n] copy number for each segment
	def get_copy_nums(self):
		cur = self.org
		bgns, ends, cps = [], [], []
		while cur != None:
			bgns.append(cur.bgn)
			ends.append(cur.end)
			cps.append(len(cur.children))
			cur = cur.r
		return bgns, ends, cps

	#  input: cov (int) coverage. number of reads the average position should have mapping to it
	#         read_len (int) length of a single random read
	# output: svs (dict) key is breakpoint tuple. this contains position (int) and isLeft (bool) if segment extends left
	#                    val is dict containing the following key-value pairs
	#                        k: mate,       v: (breakpoint tuple) same (pos, isLeft) tuple but for mate
	#                        k: mated_reads v: (int) number of reads containing this breakpoint and mate breakpoint
	#                        k: total_reads v: (int) number of total reads ()
	def get_sv_read_nums(self, cov, read_len):
		if read_len % 2 == 0: # ensure read length is odd (so it has a center)
			read_len += 1
		n = len(self.chrm)
		num_reads = int(math.ceil(float(n) / float(read_len) * float(cov)))
		positions = range(0, n)
		ps = [ random.choice(positions) for _ in xrange(0, num_reads) ] # get center positions of reads
		ps.sort()

		d = read_len / 2 # distance to be subtracted / added to get to position of edge of read
		cur = self.mut
		svs = {}
		i = 1
		while cur != None and ps:
			p = ps.pop(0) # remove next position from list
			pl, pr = p - d, p + d

			if cur.end < p:
				cur = cur.r
			if cur == None:
				break

			if _is_between(cur.bgn, pl, pr):
				_add_sv_to_dict(svs, cur, True)
			if _is_between(cur.end, pl, pr):
				_add_sv_to_dict(svs, cur, False)

		# remove any splits that are not actually breakpoints
		keys_to_remove = []
		for k, v in svs.items():
			if 'mate' not in v:
				keys_to_remove.append(k)
		for k in keys_to_remove:
			del svs[k]
		
		return svs

	def inv(self, bgn, end):
		if not self._is_in_bounds(bgn, end) or not self._is_splitable(bgn, end):
			return False
		self._2split(bgn, end) # split mutated and original list nodes at bgn and end positions

		self._rev_mut(bgn, end)

		s1, s2, s3 = tri_split_str(self.chrm, bgn, end)
		self.chrm = s1 + s2[::-1] + s3

		return True

	def rem(self, bgn, end):
		if not self._is_in_bounds(bgn, end) or not self._is_splitable(bgn, end):
			return False
		self._2split(bgn, end) # split mutated and original list nodes at bgn and end positions

		head, tail = _get_head_tail(self.mut, bgn, end)
		newL = head.l
		newR = tail.r

		if newL == None:
			self.mut = newR # change the head of the mut list to right of tail if we are removing head -> tail
		if newL != None:
			newL.r = newR
		if newR != None:
			newR.l = newL
		head.l = None
		tail.r = None

		# remove old nodes from OrgNode children list and delete old nodes
		while head != None:
			head.parent.children.remove(head) # remove curent MutNode from children list of OrgNode
			prev = head
			head = head.r
			del prev

		# decrement bgn and end values for segments to right of deleted region
		seg_len = end - bgn + 1
		cur = newR
		while cur != None:
			cur.bgn -= seg_len
			cur.end -= seg_len
			cur = cur.r

		s1, s2, s3 = tri_split_str(self.chrm, bgn, end)
		self.chrm = s1 + s3

		return True

	# duplicate region from bgn to end. returns boolean for complete or not
	def amp(self, bgn, end):
		if not self._is_in_bounds(bgn, end) or not self._is_splitable(bgn, end):
			return False
		self._2split(bgn, end) # split mutated and original list nodes at bgn and end positions

		insR, head, tail = _copy_from_to(self.mut, bgn, end) # copy list from bgn to end
		insL = insR.r # node to go after tail
		insR.r = head
		head.l = insR
		tail.r = insL
		if insL != None:
			insL.l = tail

		# increment bgn and end values for inserted region and segments to right
		seg_len = end - bgn + 1
		while head != None:
			head.bgn += seg_len
			head.end += seg_len
			head = head.r

		# duplicate string
		s1, s2, s3 = tri_split_str(self.chrm, bgn, end)
		self.chrm = s1 + s2 + s2 + s3
		return True

	# split bgn and end positions if needed. do not need to split at start or terminal of chromosome
	def _2split(self, bgn, end):
		n = len(self.chrm)
		if bgn > 0:
			self._split(bgn)     # do not split if bgn is 0 (start of chrm)
		if end + 1 < n:
			self._split(end + 1) # do not split if end is n-1 (end of chrm)

	# splits node at position k in mut and org. k is bgn of right offspring
	def _split(self, k):

		# return if k out of bounds
		if k == 0 or k >= len(self.chrm):
			printerr('cannot split at k = ' + str(k) + '\n')
			return

		# find orgNode corresponding to the mutNode where split will occur
		splitMut = self.mut
		while splitMut != None and not (splitMut.bgn <= k and k <= splitMut.end):
			splitMut = splitMut.r
		orgNode1 = splitMut.parent

		if splitMut.bgn == k or splitMut.end == k: # should not split b/c this was already split
			return

		k = k - splitMut.bgn # make k the new length of the old node (node that will be split)
		                     # is is now the number of nucletides in from a node where it should be split

		# split orgNode1 and all its children
		orgNode2 = orgNode1.split(k)
		for mutNode1 in orgNode1.children:
			mutNode2 = mutNode1.split(k)
			mutNode2.parent = orgNode2
			orgNode2.children.append(mutNode2)

	def _is_in_bounds(self, bgn, end):
		n = len(self.chrm)
		if bgn < 0 or bgn > end or end >= n:
			printerr('chromosome has length ' + str(n) + '. cannot mutate [' + str(bgn) + ', ' + str(end) + ']')
			return False
		return True

	# returns True if bgn and end do not match any positions already in mutated list
	def _is_splitable(self, bgn, end):
		n = len(self.chrm)
		if bgn != 0 and _is_already_mut_bgn(self.mut, bgn):
			return False
		if end + 1 < n and _is_already_mut_end(self.mut, end):
			return False
		return True

	# returns original node that has a mutant at position pos
	def _get_orgNode_mut_pos(pos):
		cur = self.mut
		while cur != None:
			if cur.bgn >= pos and cur.end <= pos:
				return cur.parent
			cur = cur.r
		return None

	# reverses doubly linked list starting from node with bgn of bgn to node with end of end
	def _rev_mut(self, bgn, end):
		cur = self.mut
		while cur != None and cur.bgn != bgn: # node with bgn should exist
			cur = cur.r
		ih = cur   # inner head
		oh = cur.l # outer head
		while cur != None and cur.end != end: # node with end should exist
			cur = cur.r
		it = cur   # inner tail
		ot = cur.r # outer tail

		# set region bgn and end for calculating new positions of segments
		rgbgn, rgend = ih.bgn, it.end
		
		cur = ih
		while cur != ot: # reverse linked list ih -> ... -> it
			prv = cur.l
			nxt = cur.r
			cur.l = nxt
			cur.r = prv
			pos_diff = _get_inv_pos_diff(rgbgn, rgend, cur.bgn, cur.end)
			cur.bgn += pos_diff
			cur.end += pos_diff
			cur.is_inv = not cur.is_inv
			cur = nxt

		it.l = oh      # connect head and tail of internally reversed linked list to outer list
		ih.r = ot
		if oh != None:
			oh.r = it
		if ot != None:
			ot.l = ih

		if oh == None:
			self.mut = it # set head of mut if we inverted start of list

	def pprint(self):
		printnow('sequence: ' + str(self.chrm) + '\n')
		printnow('lists:\n')
		for lst_name, cur in {'org': self.org, 'mut': self.mut}.iteritems():
			printnow(lst_name + ': ')
			while cur != None:
				cur.pprint()
				cur = cur.r
			printnow('\n')
		printnow('relations:\n')
		cur = self.org
		while cur != None:
			kid_pos_strs = [ kid.get_pos_str() for kid in cur.children ]
			printnow('[' + str(cur.bgn) + ',' + str(cur.end) + '] -> ' + ', '.join(kid_pos_strs) + '\n')
			cur = cur.r
		printnow('copy numbers: ' + str(self.get_copy_nums()[2]) + '\n')

class _Node:
	def pprint(self):
		s = self.get_pos_str()
		if self.r != None:
			s += '->'
		else:
			s += '-v'
		printnow(s)
	def get_pos_str(self):
		return '[' + str(self.bgn) + ',' + str(self.end) + ']'

class _OrgNode(_Node):
	def __init__(self, bgn, end):
		self.children = [] # no mutated sections
		self.l = None      # no left or right pointers
		self.r = None
		self.bgn = bgn
		self.end = end

	# returns pointer to new sibling on right. k (int) means k + self.begin is bgn of new sibling
	def split(self, k):
		r = self.r
		self.r = _OrgNode(self.bgn + k, self.end)
		self.r.r = r    # set right of new node to the old node's old right
		self.r.l = self # set left of new node to old node (self)
		if r != None:
			r.l = self.r
		self.end = self.bgn + k - 1
		return self.r

class _MutNode(_Node):
	def __init__(self, bgn, end, is_inv = False):
		self.parent = None
		self.l = None
		self.r = None
		self.bgn = bgn
		self.end = end
		self.is_inv = is_inv

	# returns pointer to new sibling on right. k (int) means k + self.begin is bgn of new sibling
	def split(self, k):
		r = self.r
		self.r = _MutNode(self.bgn + k, self.end, self.is_inv)
		self.r.r = r    # set right of new node to the old node's old right
		self.r.l = self # set left of new node to old node (self)
		if r != None:
			r.l = self.r
		self.end = self.bgn + k - 1
		return self.r

	def get_pos_str(self):
		if self.is_inv:
			return 'i[' + str(self.bgn) + ',' + str(self.end) + ']'
		return '[' + str(self.bgn) + ',' + str(self.end) + ']'

# helpers

# head is MutNode with bgn and tail is MutNode with end. must _2split() before so these exist!
def _get_head_tail(cur, bgn, end):
	while cur != None and cur.bgn != bgn:
		cur = cur.r
	head = cur
	while cur != None and cur.end != end:
		cur = cur.r
	tail = cur
	return head, tail

# cur (mutNode). returns True if bgn is already in mutNode list
def _is_already_mut_bgn(cur, bgn):
	while cur != None:
		if bgn == cur.bgn:
			return True
		cur = cur.r
	return False
def _is_already_mut_end(cur, end):
	while cur != None:
		if end == cur.end:
			return True
		cur = cur.r
	return False

# fm (int) is bgn index of one of the nodes. to (int) is end of one of the nodes
def _copy_from_to(head, fm, to):
	while head != None and head.bgn != fm: # make head the beggining of where to copy
		head = head.r

	curA = head
	i = 0
	prevB = None
	while curA != None:
		curB = copy.copy(curA)
		curB.parent.children.append(curB) # update parent's children pointers
		if i == 0:
			headB = curB
			i += 1
		curB.l = prevB
		if prevB != None:
			prevB.r = curB
		curB.r = None
		prevB = curB
		if curA.end == to:
			return curA, headB, curB
		curA = curA.r
	printerr('should not get here')

#  input: rgbgn (int) region beginning. position of bgn for first node of list to be inverted
#         rgend (int) region ending.    position of end for last  node of list to be inverted
#         sgbgn (int) segment beginning. bgn of current segment being flipped
#         sgend (int) segment ending.    end of current segment being flipped
# output: d (int) change in position to be applied to bgn and end of current node
def _get_inv_pos_diff(rgbgn, rgend, sgbgn, sgend):
	rglen = rgend - rgbgn + 1                            # region length
	sglen = sgend - sgbgn + 1                            # segment length
	mid = int(math.ceil(float(rglen) / 2.0) + rgbgn - 1) # position of midpoint of region
	l = mid - sgend                                      # distance from midpoint to segment ending
	if rglen % 2 == 0: # even
		return 2 * l + sglen
	return 2 * l + sglen - 1

def tri_split_str(s, bgn, end):
	s1 = s[:bgn]
	s2 = s[bgn:end+1]
	s3 = s[end+1:]
	return s1, s2, s3

# returns True if x is between a and b inclusive
def _is_between(x, a, b):
	return (a <= x) and (x <= b)

#  input: cur (MutNode) current mutant node the read maps to
#         isBgn (bool) True if read mapped to cur.bgn. False if mapped to cur.end
# output: pos (int) mate OrgNode's bgn or end position (depends on isBgn). this is position of mate bp
#         isLeft (bool) mate OrgNode's orientation. True if cur was found next to end on mate. False if
#                                                           cur was found next to bgn on mate
#         isAdj (bool) True if mate is adjacent to cur in original genome. this will not increment num mated reads
def _get_mated_pos(cur, isBgn):
	mate = cur.r
	if isBgn:
		mate = cur.l

	if mate == None:
		return None, None, None

	curPos = _get_org_pos(cur, isBgn)
	matePos = _get_org_pos(mate, not isBgn)

	isLeft = mate.parent.end == matePos
	isAdj = abs(curPos - matePos) == 1

	return matePos, isLeft, isAdj

# node (MuteNode), isBgn (bool) True if considering left pos on mutant. returns position of org node
def _get_org_pos(node, isBgn):
	if node.is_inv:
		isBgn = not isBgn
	if isBgn:
		return node.parent.bgn
	return node.parent.end

def _get_cur_pos(cur, isBgn):
	oCur = cur.parent
	isLeft = not isBgn
	if cur.is_inv:
		isLeft = not isLeft
	if isLeft:
		return oCur.end, isLeft
	return oCur.bgn, isLeft

def _add_sv_to_dict(svs, cur, isBgn):
	matePos, mateIsLeft, isAdj = _get_mated_pos(cur, isBgn)
	curPos, curIsLeft = _get_cur_pos(cur, isBgn)
	if matePos == None:
		return

	curTup = (curPos, curIsLeft)
	mateTup = (matePos, mateIsLeft)

	if matePos != None:
		if curTup not in svs:
			svs[curTup] = {'total_reads': 0, 'mated_reads': 0}

		if mateTup not in svs:
			svs[mateTup] = {'total_reads': 0, 'mated_reads': 0}

		svs[curTup]['total_reads'] += 1

		if not isAdj:
			svs[curTup]['mated_reads'] += 1
			svs[curTup]['mate'] = mateTup
			svs[mateTup]['mate'] = curTup
