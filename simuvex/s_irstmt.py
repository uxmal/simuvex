#!/usr/bin/env python
'''This module handles constraint generation for VEX IRStmt.'''

import symexec
import s_helpers
from .s_value import SimValue
from .s_irexpr import SimIRExpr

import logging
l = logging.getLogger("s_irstmt")

class UnsupportedIRStmtType(Exception):
	pass

# A class for symbolically translating VEX IRStmts.
class SimIRStmt:
	def __init__(self, stmt, imark, state, options):
		self.stmt = stmt
		self.imark = imark

		self.state = state
		self.state.id = "%x" % imark.addr

		# the options and mode
		self.options = options

		# references by the statement
		self.code_refs = [ ]
		self.data_reads = [ ]
		self.data_writes = [ ]
		self.memory_refs = [ ]

		# for concrete mode, whether or not the exit was taken
		self.concrete_exit_taken = False

		if "concrete" in self.options: mode = "concrete"
		elif "symbolic" in self.options: mode = "symbolic"

		func_name = mode + "_" + type(stmt).__name__
		if hasattr(self, func_name):
			l.debug("Handling IRStmt %s in %s mode" % (type(stmt), mode))
			getattr(self, func_name)(stmt)
		else:
			raise UnsupportedIRStmtType("Unsupported statement type %s in %s mode." % (type(stmt), mode))

	def record_expr_refs(self, expr):
		# first, track data reads
		self.data_reads.extend([ r for r in expr.data_reads if not r[0].is_symbolic() ])

		# then, see if the expression references some memory
		if expr.expr and ('symbolic' in self.options or not expr.sim_value.is_symbolic()) and expr.sim_value in self.state.memory and expr.sim_value.any() != self.imark.addr + self.imark.len:
			self.memory_refs.append(expr.sim_value)

	# translates an IRExpr into a SimIRExpr, honoring the state, mode, and options of this statement
	def translate_expr(self, expr):
		return SimIRExpr(expr, self.state, self.options)

	#################################
	### Static statement handlers ###
	#################################
	def concrete_NoOp(self, stmt):
		pass
	
	def concrete_IMark(self, stmt):
		pass
	
	def concrete_WrTmp(self, stmt):
		# get data and track data reads
		data = self.translate_expr(stmt.data)
		self.record_expr_refs(data)

		# SimIRexpr.expr can be None in concrete mode
		if data.expr is not None:
			self.state.temps[stmt.tmp] = data.sim_value.expr

	# TODO: make this exclude memory references made in the IP
	def concrete_Put(self, stmt):
		# first, get the data to put
		data = self.translate_expr(stmt.data)
		self.record_expr_refs(data)

		# do the put
		if data.expr is not None and "puts" in self.options:
			self.state.registers.store(stmt.offset, data.expr)

	def concrete_Store(self, stmt):
		# resolve the address
		addr = self.translate_expr(stmt.addr)
		self.record_expr_refs(addr)

		# get the value
		data = self.translate_expr(stmt.data)
		self.record_expr_refs(data)

		# track/do the write
		if not addr.sim_value.is_symbolic():
			self.data_writes.append((addr.sim_value, data.sim_value.size()))

			# do the write if the option is set
			if "stores" in self.options:
				data_val = s_helpers.fix_endian(stmt.endness, data.expr)
				self.state.memory.write_to(addr.sim_value.any(), data_val)

	# pylint: disable=R0201
	def concrete_CAS(self, stmt):
		# TODO: implement concrete CAS
		raise UnsupportedIRStmtType("Unsupported statement type %s in concrete mode." % type(stmt))

	def concrete_Exit(self, stmt):
		# the exit guard
		guard = self.translate_expr(stmt.guard)
		self.record_expr_refs(guard)

		# the destination
		dst = SimValue(s_helpers.translate_irconst(stmt.dst))
		self.code_refs.append(dst)

		if "determine_exits" in self.options and not guard.sim_value.is_symbolic() and guard.sim_value.any():
			self.concrete_exit_taken = True

	def concrete_AbiHint(self, stmt):
		# TODO: determine if this needs to do something
		pass

	#def concrete_CAS(self, stmt):
	#	#
	#	# figure out if it's a single or double
	#	#
	#	double_element = (stmt.oldHi != 0xFFFFFFFF) and (stmt.expdHi is not None)
	#
	#	#
	#	# first, get the address
	#	#
	#	addr = SimIRExpr(stmt.addr, self.state, mode="concrete").sim_value.bitvecval()
	#
	#	#
	#	# translate the expected values
	#	#
	#	expd_lo = SimIRExpr(stmt.expdLo, self.state, mode="concrete").sim_value.bitvecval()
	#	if double_element:
	#		expd_hi = SimIRExpr(stmt.expdHi, self.state, mode="concrete").sim_value.bitvecval()
	#
	#	# size of the elements
	#	element_size = expd_lo.size()
	#
	#	# the two places to write
	#	addr_first = addr
	#	addr_second = addr + element_size
	#
	#	#
	#	# Get the memory offsets
	#	#
	#	if not double_element:
	#		# single-element case
	#		addr_lo = addr_first
	#		addr_hi = None
	#	elif stmt.endness == "Iend_BE":
	#		# double-element big endian
	#		addr_hi = addr_first
	#		addr_lo = addr_second
	#	else:
	#		# double-element little endian
	#		addr_hi = addr_second
	#		addr_lo = addr_first
	#
	#	#
	#	# save the old value
	#	#
	#
	#	# save old lo
	#	old_lo = self.state.memory.load(addr_lo, element_size)
	#	old_lo = s_helpers.fix_endian(stmt.endness, old_lo)
	#	self.state.temps[stmt.oldLo] = old_lo

	#	# save old hi
	#	if double_element:
	#		old_hi = self.state.memory.load(addr_hi, element_size)
	#		old_hi = s_helpers.fix_endian(stmt.endness, old_hi)
	#		self.state.temps[stmt.oldHi] = old_hi

	#	#
	#	# comparator for compare
	#	#
	#	comparator = old_lo == expd_lo
	#	if double_element: comparator = comparator and old_hi == expd_hi

	#	#
	#	# the value to write
	#	#
	#	data_lo, data_lo_constraints = SimIRExpr(stmt.dataLo, self.state).expr_and_constraints()
	#	self.state.add_constraints(*data_lo_constraints)
	#	data_lo = s_helpers.fix_endian(stmt.endness, data_lo)

	#	if double_element:
	#		data_hi, data_hi_constraints = SimIRExpr(stmt.dataHi, self.state).expr_and_constraints()
	#		self.state.add_constraints(*data_hi_constraints)
	#		data_hi = s_helpers.fix_endian(stmt.endness, data_hi)

	#	# combine it to the ITE
	#	if not double_element:
	#		write_val = symexec.If(comparator, data_lo, old_lo)
	#	elif stmt.endness == "Iend_BE":
	#		write_val = symexec.If(comparator, symexec.Concat(data_hi, data_lo), symexec.Concat(old_hi, old_lo))
	#	else:
	#		write_val = symexec.If(comparator, symexec.Concat(data_lo, data_hi), symexec.Concat(old_lo, old_hi))

	#	#
	#	# and now write
	#	#
	#	self.state.memory.store(addr_first, write_val, self.state.constraints_after())

	###################################
	### Symbolic statement handlers ###
	###################################
	def symbolic_NoOp(self, stmt):
		pass
	
	def symbolic_IMark(self, stmt):
		pass
	
	def symbolic_WrTmp(self, stmt):
		t = self.state.temps[stmt.tmp]
		data = self.translate_expr(stmt.data)

		# track constraints
		self.state.add_constraints(t == data.expr)
		self.state.add_constraints(*data.constraints)

		# track memory reads
		self.data_reads.extend(data.data_reads)
	
	def symbolic_Put(self, stmt):
		# value to put
		data = self.translate_expr(stmt.data)
		self.state.add_constraints(*data.constraints)

		# where to put it
		offset_vec = symexec.BitVecVal(stmt.offset, self.state.arch.bits)
		offset_val = SimValue(offset_vec)

		store_constraints = self.state.registers.store(offset_val, data.expr)
		self.state.add_constraints(*store_constraints)

		# track memory reads
		self.data_reads.extend(data.data_reads)
	
	def symbolic_Store(self, stmt):
		# first resolve the address
		addr = self.translate_expr(stmt.addr)
		self.state.add_constraints(*addr.constraints)

		# now get the value
		data = self.translate_expr(stmt.data)
		data_val = s_helpers.fix_endian(stmt.endness, data.expr)
		self.state.add_constraints(*data.constraints)

		addr.sim_value.push_constraints(*data.constraints)
		store_constraints = self.state.memory.store(addr.sim_value, data_val)
		addr.sim_value.pop_constraints()

		self.state.add_constraints(*store_constraints)

		# track memory reads and writes
		self.data_reads.extend(addr.data_reads)
		self.data_reads.extend(data.data_reads)
		self.data_writes.append(( addr.sim_value, data_val.size() ))

	def symbolic_CAS(self, stmt):
		#
		# figure out if it's a single or double
		#
		double_element = (stmt.oldHi != 0xFFFFFFFF) and (stmt.expdHi is not None)

		#
		# first, get the expression of the add
		#
		addr_expr = self.translate_expr(stmt.addr)
		self.state.add_constraints(*addr_expr.constraints)

		#
		# now concretize the address, since this is going to be a write
		#
		addr = self.state.memory.concretize_write_addr(addr_expr.sim_value)[0]
		self.state.add_constraints(addr_expr.expr == addr)

		#
		# translate the expected values
		#
		expd_lo = self.translate_expr(stmt.expdLo)
		self.state.add_constraints(*expd_lo.constraints)
		if double_element:
			expd_hi = self.translate_expr(stmt.expdHi)
                	self.state.add_constraints(*expd_hi.constraints)

		# size of the elements
		element_size = expd_lo.expr.size()

		# the two places to write
		addr_first = SimValue(symexec.BitVecVal(addr, self.state.arch.bits))
		addr_second = SimValue(symexec.BitVecVal(addr + element_size, self.state.arch.bits))

		#
		# Get the memory offsets
		#
		if not double_element:
			# single-element case
			addr_lo = addr_first
			addr_hi = None
		elif stmt.endness == "Iend_BE":
			# double-element big endian
			addr_hi = addr_first
			addr_lo = addr_second
		else:
			# double-element little endian
			addr_hi = addr_second
			addr_lo = addr_first

		#
		# save the old value
		#

		# load lo
		old_lo, old_lo_constraints = self.state.memory.load(addr_lo, element_size)
		old_lo = s_helpers.fix_endian(stmt.endness, old_lo)
		self.state.add_constraints(*old_lo_constraints)

		# save it to the tmp
		old_lo_tmp = self.state.temps[stmt.oldLo]
		self.state.add_constraints(old_lo_tmp == old_lo)

		# load hi
		old_hi, old_hi_constraints = None, [ ]
		if double_element:
			old_hi, old_hi_constraints = self.state.memory.load(addr_hi, element_size)
			old_hi = s_helpers.fix_endian(stmt.endness, old_hi)
			self.state.add_constraints(*old_hi_constraints)

			# save it to the tmp
			old_hi_tmp = self.state.temps[stmt.oldHi]
			self.state.add_constraints(old_hi_tmp == old_hi)

		#
		# comparator for compare
		#
		comparator = old_lo == expd_lo.expr
		if old_hi: comparator = symexec.And(comparator, old_hi.expr == expd_hi.expr)

		#
		# the value to write
		#
		data_lo = self.translate_expr(stmt.dataLo)
		data_lo_val = s_helpers.fix_endian(stmt.endness, data_lo)
		self.state.add_constraints(*data_lo.constraints)

		if double_element:
			data_hi = self.translate_expr(stmt.dataHi)
			data_hi_val = s_helpers.fix_endian(stmt.endness, data_hi)
			self.state.add_constraints(*data_hi.constraints)

		# combine it to the ITE
		if not double_element:
			write_val = symexec.If(comparator, data_lo_val, old_lo)
		elif stmt.endness == "Iend_BE":
			write_val = symexec.If(comparator, symexec.Concat(data_hi_val, data_lo_val), symexec.Concat(old_hi, old_lo))
		else:
			write_val = symexec.If(comparator, symexec.Concat(data_lo_val, data_hi_val), symexec.Concat(old_lo, old_hi))

		#
		# and now write
		#
		self.state.memory.store(addr_first, write_val)

		# track memory reads
		self.data_reads.extend(data_lo.data_reads)
		if double_element: self.data_reads.extend(data_hi.data_reads)
		self.data_reads.extend(expd_lo.data_reads)
		if double_element: self.data_reads.extend(expd_hi.data_reads)

		# TODO: track the CAS memory write (how?)

	def symbolic_Exit(self, stmt):
		guard = self.translate_expr(stmt.guard)
		self.state.add_branch_constraints(guard.expr != 0)
		self.state.add_constraints(*guard.constraints)

		# track memory reads
		self.data_reads.extend(guard.data_reads)

		# TODO: update instruction pointer

	def symbolic_AbiHint(self, stmt):
		# TODO: determine if this needs to do something
		pass