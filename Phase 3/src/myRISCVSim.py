"""
The project is developed as part of Computer Architecture class.
Project Name: Functional Simulator for subset of RISC-V Processor

-------------------------------------------------
| Developer's Name   | Developer's Email ID     |
|-----------------------------------------------|
| Akhil Arya         | 2019csb1066@iitrpr.ac.in |
| Harshwardhan Kumar | 2019csb1089@iitrpr.ac.in |
| Krithika Goyal     | 2019csb1094@iitrpr.ac.in |
| Rhythm Jain        | 2019csb1111@iitrpr.ac.in |
| Tarun Singla       | 2019csb1126@iitrpr.ac.in |
-------------------------------------------------
"""

# myRISCVSim.py
# Purpose of this file: This file contains all the classes and functions used for the simulator.

from collections import defaultdict
from sys import exit
import os
import csv


# Utility Functions
def nhex(num):
	if num < 0:
		num += 2**32
	return hex(num)

def nint(s, base, bits=32):
	num = int(s, base)
	if num >= 2**(bits-1):
		num -= 2**bits
	return num

def sign_extend(data):
	if data[2] == '8' or data[2] == '9' or data[2] == 'a' or data[2] == 'b' or data[2] == 'c' or data[2] == 'd' or data[2] == 'e' or data[2] == 'f':
		data = data[:2] + (10 - len(data)) * 'f' + data[2:]
	else:
		data = data[:2] + (10 - len(data)) * '0' + data[2:]
	return data


# Instruction/State Class
class State:
	def __init__(self, pc = 0):
		self.PC = pc
		self.instruction_word = '0x0'
		self.rs1 = -1
		self.rs2 = -1
		self.operand1 = 0
		self.operand2 = 0
		self.rd = -1
		self.offset = 0
		self.register_data = '0x00000000'
		self.memory_address = 0
		self.alu_control_signal = -1
		self.is_mem = [-1, -1] # [-1/0/1(no memory operation/load/store), type of load/store if any]
		self.write_back_signal = False
		#
		self.is_dummy = False
		self.pc_update = -1
		self.branch_taken = False
		#
		self.inc_select = 0
		self.pc_select = 0
		self.pc_offset = 0
		self.return_address = -1
		self.next_pc = -1
		#
		self.decode_forwarding_op1 = False
		self.decode_forwarding_op2 = False
		self.asm_code = ''


# Brach table buffer
class BTB:
	def __init__(self):
		self.table = {}

	def find(self, pc):
		if pc in self.table.keys():
			return True
		return False

	def enter(self, type, pc, to_take_address):
		if type:
			self.table[pc] = [True, to_take_address]
		elif to_take_address > pc:
			self.table[pc] = [False, to_take_address]
		else:
			self.table[pc] = [True, to_take_address]

	def predict(self, pc):
		return self.table[pc][0]

	def getTarget(self, pc):
		return self.table[pc][1]


# Processor
class Processor:
	def __init__(self, file_name, data_cache, instruction_cache):
		self.MEM = defaultdict(lambda: '00')
		self.data_cache = data_cache
		self.instruction_cache = instruction_cache
		self.R = ['0x00000000' for i in range(32)]
		self.R[2] = '0x7FFFFFF0'
		self.R[3] = '0x10000000'
		self.load_program_memory(file_name)
		self.pipelining_enabled = False
		self.terminate = False
		self.next_PC = 0
		self.inc_select = 0
		self.pc_select = 0
		self.return_address = -1
		self.pc_offset = 0
		# Various Counts
		self.count_total_inst = 0
		self.count_alu_inst = 0
		self.count_mem_inst = 0
		self.count_control_inst = 0
		self.count_branch_mispredictions = 0
		self.all_dummy = False
		# gui variable
		self.get_code = defaultdict(lambda: -1)


	def reset(self, *args):
		if len(args) > 0:
			state = args[0]
			state.inc_select = 0
			state.pc_select = 0
			state.pc_offset = 0
			state.return_address = 0

		else:
			self.inc_select = 0
			self.pc_select = 0
			self.pc_offset = 0
			self.return_address = 0


	# load_program_memory reads the input memory, and populates the instruction memory
	def load_program_memory(self, file_name):
		try:
			fp = open(file_name, 'r')
			for line in fp:
				tmp = line.split()
				if len(tmp) == 2:
					address, instruction = tmp[0], tmp[1]
					self.write_word(address, instruction)
			fp.close()
		except:
			print("ERROR: Error opening input .mc file\n")
			exit(1)


	# Memory write
	def write_word(self, address, instruction):
		idx = int(address[2:], 16)
		self.MEM[idx] =  instruction[8:10]
		self.MEM[idx + 1] = instruction[6:8]
		self.MEM[idx + 2] = instruction[4:6]
		self.MEM[idx + 3] = instruction[2:4]


	# Creates a "data_out.mc" file and writes the data memory in it. It also creates
	# a reg_out.mc file and writes the contents of registers in it.
	def write_data_memory(self):
		try:
			fp = open("data_out.mc", "w")
			out_tmp = []
			for i in range(268435456, 268468221, 4):
				out_tmp.append(
					hex(i) + ' 0x' + self.MEM[i + 3] + self.MEM[i + 2] + self.MEM[i + 1] + self.MEM[i] + '\n')
			fp.writelines(out_tmp)
			fp.close()
		except:
			print("ERROR: Error opening data_out.mc file for writing\n")
			exit(1)

		try:
			fp = open("reg_out.mc", "w")
			out_tmp = []
			for i in range(32):
				out_tmp.append('x' + str(i) + ' ' + self.R[i] + '\n')
			fp.writelines(out_tmp)
			fp.close()
		except:
			print("ERROR: Error opening reg_out.mc file for writing\n")
			exit(1)


	# Instruction address generator
	def IAG(self, state):
		if state.pc_select:
			self.next_PC = state.return_address
		elif state.inc_select:
			self.next_PC += state.pc_offset
		else:
			self.next_PC += 4

		state.pc_select = 0
		state.inc_select = 0


	# Reads from the instruction memory and updates the instruction register
	def fetch(self, state, *args):
		if state.is_dummy:
			return

		if self.all_dummy:
			state.is_dummy = True
			return

		data, gui_read = self.instruction_cache.read(state.PC, self.MEM)
		state.instruction_word = '0x' + data[6:8] + data[4:6] + data[2:4] + data[0:2]
    
		if not self.pipelining_enabled:
			return gui_read

		btb = args[0]

		if btb.find(state.PC):
			state.branch_taken = btb.predict(state.PC)
			if state.branch_taken:
				state.next_pc = btb.getTarget(state.PC)
			else:
				state.next_pc = state.PC + 4
		return gui_read


	# Decodes the instruction and decides the operation to be performed in the execute stage; reads the operands from the register file.
	def decode(self, state, *args):
		if state.is_dummy:
			return False, 0, False, 0

		if state.instruction_word == '0x401080BB':
			self.terminate = True
			state.is_dummy = True
			self.all_dummy = True
			return False, 0, False, 0

		bin_instruction = bin(int(state.instruction_word[2:], 16))[2:]
		bin_instruction = (32 - len(bin_instruction)) * '0' + bin_instruction

		opcode = int(bin_instruction[25:32], 2)
		func3 = int(bin_instruction[17:20], 2)
		func7 = int(bin_instruction[0:7], 2)

		path = os.path.dirname(__file__)
		f = open(os.path.join(path,'Instruction_Set_List.csv'))
		instruction_set_list = list(csv.reader(f))
		f.close()

		match_found = False
		track = 0

		for ins in instruction_set_list:
			if track == 0:
				match_found = False
			elif ins[4] != 'NA' and [int(ins[2], 2), int(ins[3], 2), int(ins[4], 2)] == [opcode, func3, func7]:
				match_found = True
			elif ins[4] == 'NA' and ins[3] != 'NA' and [int(ins[2], 2), int(ins[3], 2)] == [opcode, func3]:
				match_found = True
			elif ins[4] == 'NA' and ins[3] == 'NA' and int(ins[2], 2) == opcode:
				match_found = True
			if match_found:
				break
			track += 1

		if not match_found:
			print(bin_instruction, state.instruction_word, opcode, func3, func7)
			print("ERROR: Unidentifiable machine code!\n")
			exit(1)

		op_type = instruction_set_list[track][0]
		state.alu_control_signal = track

		state.is_mem = [-1, -1]

		if op_type == 'R':
			state.rs2 = bin_instruction[7:12]
			state.rs1 = bin_instruction[12:17]
			state.rd = bin_instruction[20:25]
			state.operand1 = self.R[int(state.rs1, 2)]
			state.operand2 = self.R[int(state.rs2, 2)]
			state.write_back_signal = True

		elif op_type == 'I':
			state.rs1 = bin_instruction[12:17]
			state.rd = bin_instruction[20:25]
			imm = bin_instruction[0:12]
			if not state.decode_forwarding_op1:
				state.operand1 = self.R[int(state.rs1, 2)]
			state.operand2 = imm
			state.write_back_signal = True

		elif op_type == 'S':
			state.rs2 = bin_instruction[7:12]
			state.rs1 = bin_instruction[12:17]
			imm = bin_instruction[0:7] + bin_instruction[20:25]
			if not state.decode_forwarding_op1:
				state.operand1 = self.R[int(state.rs1, 2)]
			state.operand2 = imm
			state.register_data = self.R[int(state.rs2, 2)]
			state.write_back_signal = False

		elif op_type == 'SB':
			state.rs2 = bin_instruction[7:12]
			state.rs1 = bin_instruction[12:17]
			if not state.decode_forwarding_op1:
				state.operand1 = self.R[int(state.rs1, 2)]
			if not state.decode_forwarding_op2:
				state.operand2 = self.R[int(state.rs2, 2)]
			imm = bin_instruction[0] + bin_instruction[24] + \
				bin_instruction[1:7] + bin_instruction[20:24] + '0'
			state.offset = imm
			state.write_back_signal = False

		elif op_type == 'U':
			state.rd = bin_instruction[20:25]
			imm = bin_instruction[0:20] + '0'*12
			state.write_back_signal = True
			state.operand2 = imm

		elif op_type == 'UJ':
			state.rd = bin_instruction[20:25]
			imm = bin_instruction[0] + bin_instruction[12:20] + \
				bin_instruction[11] + bin_instruction[1:11] + '0'
			state.write_back_signal = True
			state.offset = imm

		else:
			print("ERROR: Unidentifiable machine code!\n")
			exit(1)

		if self.pipelining_enabled:
			branch_ins = [23, 24, 25, 26, 29, 19]
			entering = False

			if state.alu_control_signal not in branch_ins:
				return False, 0, entering, 0

			else:
				self.execute(state)
				self.next_PC = state.PC
				self.IAG(state)
				orig_pc = self.next_PC
				btb = args[0]

				if btb.find(state.PC) and orig_pc != state.next_pc:
					self.count_branch_mispredictions += 1


				if not btb.find(state.PC):
					state.inc_select = self.inc_select
					state.pc_select = self.pc_select
					state.pc_offset = self.pc_offset
					state.return_address = self.return_address
					self.next_PC = state.PC
					self.IAG(state)
					state.pc_update = self.next_PC
					if state.alu_control_signal == 19 or state.alu_control_signal == 29:
						btb.enter(True, state.PC, state.pc_update)
					else:
						btb.enter(False, state.PC, state.pc_update)
						# entering = True if jalr is always green
					self.reset()
					self.reset(state)
					entering = True

				if orig_pc != state.next_pc:
					return True, orig_pc, entering, 1
				else:
					return False, 0, entering, 3 # 0: no_pred, 1: wrong, 3: correct


	# Executes the ALU operation based on ALUop
	def execute(self, state):
		if state.is_dummy:
			return

		if state.alu_control_signal == 2:
			state.register_data = nhex(int(nint(state.operand1, 16) + nint(state.operand2, 16)))
			state.asm_code = "add x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2))

		elif state.alu_control_signal == 8:
			state.register_data = nhex(int(nint(state.operand1, 16) - nint(state.operand2, 16)))
			state.asm_code = "sub x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2))

		elif state.alu_control_signal == 1:
			state.register_data = nhex(int(int(state.operand1, 16) & int(state.operand2, 16)))
			state.asm_code = "and x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2))

		elif state.alu_control_signal == 3:
			state.register_data = nhex(int(int(state.operand1, 16) | int(state.operand2, 16)))
			state.asm_code = "or x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2))

		elif state.alu_control_signal == 4:
			if(nint(state.operand2, 16) < 0):
				print("ERROR: Shift by negative!\n")
				exit(1)
			else:
				state.register_data = nhex(int(int(state.operand1, 16) << int(state.operand2, 16)))
			state.asm_code = "sll x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2))

		elif state.alu_control_signal == 5:
			if (nint(state.operand1, 16) < nint(state.operand2, 16)):
				state.register_data = hex(1)
			else:
				state.register_data = hex(0)
			state.asm_code = "slt x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2))

		elif state.alu_control_signal == 6:
			if(nint(state.operand2, 16) < 0):
				print("ERROR: Shift by negative!\n")
				exit(1)
			else:
				state.register_data = bin(int(int(state.operand1, 16) >> int(state.operand2, 16)))
				if state.operand1[2] == '8' or state.operand1[2] == '9' or state.operand1[2] == 'a' or state.operand1[2] == 'b' or state.operand1[2] == 'c' or state.operand1[2] == 'd' or state.operand1[2] == 'e' or state.operand1[2] == 'f':
					state.register_data = '0b' + (34 - len(state.register_data)) * '1' + state.register_data[2:]
				state.register_data = hex(int(state.register_data, 2))
			state.asm_code = "sra x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2))

		elif state.alu_control_signal == 7:
			if(nint(state.operand2, 16) < 0):
				print("ERROR: Shift by negative!\n")
				exit(1)
			else:
				state.register_data = nhex(int(state.operand1, 16) >> int(state.operand2, 16))
			state.asm_code = "srl x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2))

		elif state.alu_control_signal == 9:
			state.register_data = nhex(int(int(state.operand1, 16) ^ int(state.operand2, 16)))
			state.asm_code = "xor x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2))

		elif state.alu_control_signal == 10:
			state.register_data = nhex(int(nint(state.operand1, 16) * nint(state.operand2, 16)))
			state.asm_code = "mul x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2))

		elif state.alu_control_signal == 11:
			if nint(state.operand2, 16) == 0:
				print("ERROR: Division by zero!\n")
				exit(1)
			else:
				state.register_data = nhex(int(nint(state.operand1, 16) / nint(state.operand2, 16)))
			state.asm_code = "div x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2))

		elif state.alu_control_signal == 12:
			state.register_data = nhex(int(nint(state.operand1, 16) % nint(state.operand2, 16)))
			state.asm_code = "rem x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2))

		elif state.alu_control_signal == 14:
			state.register_data = nhex(
				int(nint(state.operand1, 16) + nint(state.operand2, 2, len(state.operand2))))
			state.asm_code = "addi x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1,2)) + " " + str(nint(state.operand2, 2, len(state.operand2)))

		elif state.alu_control_signal == 13:
			state.register_data = nhex(int(int(state.operand1, 16) & int(state.operand2, 2)))
			state.asm_code = "andi x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " " + str(int(state.operand2, 2))

		elif state.alu_control_signal == 15:
			state.register_data = nhex(int(int(state.operand1, 16) | int(state.operand2, 2)))
			state.asm_code = "ori x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " " + str(int(state.operand2, 2))

		elif state.alu_control_signal == 16:
			state.memory_address = int(int(state.operand1, 16) + nint(state.operand2, 2, len(state.operand2)))
			state.is_mem = [0, 0]
			state.asm_code = "lb x" + str(int(state.rd, 2)) + ' ' + str(nint(state.operand2, 2, len(state.operand2))) + " (x" + str(int(state.rs1,2)) + ")"

		elif state.alu_control_signal == 17:
			state.memory_address = int(int(state.operand1, 16) + nint(state.operand2, 2, len(state.operand2)))
			state.is_mem = [0, 1]
			state.asm_code = "lh x" + str(int(state.rd, 2)) + ' ' + str(nint(state.operand2, 2, len(state.operand2))) + " (x" + str(int(state.rs1,2)) + ")"

		elif state.alu_control_signal == 18:
			state.memory_address = int(int(state.operand1, 16) + nint(state.operand2, 2, len(state.operand2)))
			state.is_mem = [0, 3]
			state.asm_code = "lw x" + str(int(state.rd, 2)) + ' ' + str(nint(state.operand2, 2, len(state.operand2))) + " (x" + str(int(state.rs1,2)) + ")"

		elif state.alu_control_signal == 19: # Jalr
			state.register_data = nhex(state.PC + 4)
			self.return_address = nint(state.operand2, 2, len(state.operand2)) + nint(state.operand1, 16)
			self.pc_select = 1
			state.pc_select = 1
			state.return_address = nint(state.operand2, 2, len(state.operand2)) + nint(state.operand1, 16)
			state.asm_code = "jalr x" + str(int(state.rd, 2)) + " x" + str(int(state.rs1, 2)) + " " + str(nint(state.operand2, 2, len(state.operand2)))

		elif state.alu_control_signal == 20:
			state.memory_address = int(int(state.operand1, 16) + nint(state.operand2, 2, len(state.operand2)))
			state.is_mem = [1, 0]
			state.asm_code = "sb x" + str(int(state.rs2, 2)) + ' ' + str(nint(state.operand2, 2, len(state.operand2))) + " (x" + str(int(state.rs1, 2)) + ")"

		elif state.alu_control_signal == 22:
			state.memory_address = int(int(state.operand1, 16) + nint(state.operand2, 2, len(state.operand2)))
			state.is_mem = [1, 1]
			state.asm_code = "sh x" + str(int(state.rs2, 2)) + ' ' + str(nint(state.operand2, 2, len(state.operand2))) + " (x" + str(int(state.rs1, 2)) + ")"

		elif state.alu_control_signal == 21:
			state.memory_address = int(int(state.operand1, 16) + nint(state.operand2, 2, len(state.operand2)))
			state.is_mem = [1, 3]
			state.asm_code = "sw x" + str(int(state.rs2, 2)) + ' ' + str(nint(state.operand2, 2, len(state.operand2))) + " (x" + str(int(state.rs1, 2)) + ")"

		elif state.alu_control_signal == 23:
			if nint(state.operand1, 16) == nint(state.operand2, 16):
				state.pc_offset = nint(state.offset, 2, len(state.offset))
				state.inc_select = 1
			self.pc_offset = nint(state.offset, 2, len(state.offset))
			self.inc_select = 1
			state.asm_code = "beq x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2)) + " " + str(self.pc_offset)

		elif state.alu_control_signal == 24:
			if nint(state.operand1, 16) != nint(state.operand2, 16):
				state.pc_offset = nint(state.offset, 2, len(state.offset))
				state.inc_select = 1
			self.pc_offset = nint(state.offset, 2, len(state.offset))
			self.inc_select = 1
			state.asm_code = "bne x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2)) + " " + str(self.pc_offset)

		elif state.alu_control_signal == 25:
			if nint(state.operand1, 16) >= nint(state.operand2, 16):
				state.pc_offset = nint(state.offset, 2,  len(state.offset))
				state.inc_select = 1
			self.pc_offset = nint(state.offset, 2,  len(state.offset))
			self.inc_select = 1
			state.asm_code = "bge x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2)) + " " + str(self.pc_offset)

		elif state.alu_control_signal == 26:
			if nint(state.operand1, 16) < nint(state.operand2, 16):
				state.pc_offset =  nint(state.offset, 2, len(state.offset))
				state.inc_select = 1
			self.pc_offset =  nint(state.offset, 2, len(state.offset))
			self.inc_select = 1
			state.asm_code = "blt x" + str(int(state.rs1, 2)) + " x" + str(int(state.rs2, 2)) + " " + str(self.pc_offset)

		elif state.alu_control_signal == 27:
			state.register_data = nhex(int(state.PC + 4 + int(state.operand2, 2)))
			state.asm_code = "auipc x" + str(int(state.rd, 2)) + " " + str(int(state.operand2[:20], 2))

		elif state.alu_control_signal == 28:
			state.register_data = nhex(int(state.operand2, 2))
			state.asm_code = "lui x" + str(int(state.rd, 2)) + " " + str(int(state.operand2[:20], 2))

		elif state.alu_control_signal == 29: # Jal
			state.register_data = nhex(state.PC + 4)
			self.pc_offset = nint(state.offset, 2, len(state.offset))
			self.inc_select = 1
			state.pc_offset = nint(state.offset, 2, len(state.offset))
			state.inc_select = 1
			state.asm_code = "jal x" + str(int(state.rd, 2)) + " " + str(self.pc_offset)

		self.get_code[state.PC] = state.asm_code

		if len(state.register_data) > 10:
			state.register_data = state.register_data[:2] + state.register_data[-8:]

		state.register_data = state.register_data[:2] + \
			(10 - len(state.register_data)) * '0' + state.register_data[2::]


	# Performs the memory operations
	def mem(self, state):
		if not self.pipelining_enabled:
			self.IAG(state)

		if state.is_dummy:
			return False

		if state.is_mem[0] == -1:
			return False

		elif state.is_mem[0] == 0:
			state.register_data = '0x'
			data, gui_read = self.data_cache.read(state.memory_address, self.MEM)

			if state.is_mem[1] == 0:
				state.register_data += data[0:2]
			elif state.is_mem[1] == 1:
				state.register_data += data[2:4] + data[0:2]
			else:
				state.register_data += data[6:8] + data[4:6] + data[2:4] + data[0:2]

			state.register_data = sign_extend(state.register_data)
			return gui_read

		else:
			gui_write = self.data_cache.write(state.memory_address, state.register_data, self.MEM, state.is_mem[1])
			return gui_write


	# Writes the results back to the register file
	def write_back(self, state):
		if not state.is_dummy:
			self.count_total_inst += 1 # total instructions

			if state.alu_control_signal in [19, 23, 24, 25, 26, 29]:  # control instruction
				self.count_control_inst += 1

			elif state.alu_control_signal in [16, 17, 18, 20, 21, 22]: # data transfer instruction
				self.count_mem_inst += 1

			else:
				self.count_alu_inst += 1 # alu instruction

			if state.write_back_signal:
				if int(state.rd, 2) != 0:
					self.R[int(state.rd, 2)] = state.register_data


# Hazard Detection Unit, Performs operations related to data hazard, stalling and forwarding
class HDU:
	# If forwarding is not enabled
	def data_hazard_stalling(self, pipeline_instructions):
		count_data_hazard = 0
		data_hazard = False

		# since we don't have values for instruction in decode stage
		decode_state = pipeline_instructions[-2]
		bin_instruction = bin(int(decode_state.instruction_word[2:], 16))[2:]
		bin_instruction = (32 - len(bin_instruction)) * '0' + bin_instruction
		decode_opcode = int(bin_instruction[25:32], 2)
		if decode_opcode in [19, 103, 3]:
			decode_state.rs1 = bin_instruction[12:17]
			decode_state.rs2 = -1
		elif decode_opcode not in [23, 55, 111]:
			decode_state.rs1 = bin_instruction[12:17]
			decode_state.rs2 = bin_instruction[7:12]

		states_to_check = pipeline_instructions[:-1]
		gui_pair = {'who': -1, 'from_whom': -1}

		exe_state = states_to_check[-2]
		decode_state = states_to_check[-1]
		if exe_state.rd != -1 and exe_state.rd != '00000' and not exe_state.is_dummy and not decode_state.is_dummy:
			if exe_state.rd == decode_state.rs1 or exe_state.rd == decode_state.rs2:
				data_hazard = True
				count_data_hazard += 1
				gui_pair = {'who': 3, 'from_whom': 2}

		mem_state = states_to_check[-3]
		if mem_state.rd != -1 and mem_state.rd != '00000' and not mem_state.is_dummy and not decode_state.is_dummy:
			if mem_state.rd == decode_state.rs1 or mem_state.rd == decode_state.rs2:
				data_hazard = True
				count_data_hazard += 1
				gui_pair = {'who': 3, 'from_whom': 1}

		return [data_hazard, count_data_hazard, gui_pair]


	# If forwarding is enabled
	def data_hazard_forwarding(self, pipeline_instructions):
		decode_state = pipeline_instructions[-2]
		exe_state = pipeline_instructions[-3]
		mem_state = pipeline_instructions[-4]
		wb_state = pipeline_instructions[-5]

		# since we don't have values for instruction in decode stage
		bin_instruction = bin(int(decode_state.instruction_word[2:], 16))[2:]
		bin_instruction = (32 - len(bin_instruction)) * '0' + bin_instruction
		decode_opcode = int(bin_instruction[25:32], 2)
		if decode_opcode in [19, 103, 3]:
			decode_state.rs1 = bin_instruction[12:17]
			decode_state.rs2 = -1
		elif decode_opcode not in [23, 55, 111]:
			decode_state.rs1 = bin_instruction[12:17]
			decode_state.rs2 = bin_instruction[7:12]

		data_hazard = 0
		if_stall = False
		stall_position = 2
		gui_pair = {'who': -1, 'from_whom': -1}
		# codes for gui_for wb = 0, mem = 1, execute = 2, decode = 3, fetch = 4
		gui_for = [""]*5

		# getting opcodes
		bin_instruction = bin(int(exe_state.instruction_word[2:], 16))[2:]
		bin_instruction = (32 - len(bin_instruction)) * '0' + bin_instruction
		exe_opcode = int(bin_instruction[25:32], 2)

		bin_instruction = bin(int(mem_state.instruction_word[2:], 16))[2:]
		bin_instruction = (32 - len(bin_instruction)) * '0' + bin_instruction
		mem_opcode = int(bin_instruction[25:32], 2)

		bin_instruction = bin(int(wb_state.instruction_word[2:], 16))[2:]
		bin_instruction = (32 - len(bin_instruction)) * '0' + bin_instruction
		wb_opcode = int(bin_instruction[25:32], 2)

		# M -> M forwarding
		if wb_opcode == 3 and mem_opcode == 35 and not wb_state.is_dummy and not mem_state.is_dummy: # 3 == load and 35 == store
			if wb_state.rd != -1 and wb_state.rd != '00000' and wb_state.rd == mem_state.rs2:
				mem_state.register_data = wb_state.register_data
				data_hazard += 1
				gui_pair = {'who': -1, 'from_whom': -1}
				gui_for[1] = "forwarded from mem"

		# M -> E forwarding
		if wb_state.rd != -1 and wb_state.rd != '00000' and not wb_state.is_dummy:
			if wb_state.rd == exe_state.rs1 and not exe_state.is_dummy:
				exe_state.operand1 = wb_state.register_data
				data_hazard += 1
				gui_pair = {'who': -1, 'from_whom': -1}
				gui_for[2] = "forwarded from mem"

			if wb_state.rd == exe_state.rs2 and not exe_state.is_dummy:
				if exe_opcode != 35: # store
					exe_state.operand2 = wb_state.register_data
				else:
					exe_state.register_data = wb_state.register_data
				data_hazard += 1
				gui_pair = {'who': -1, 'from_whom': -1}
				gui_for[2] = "forwarded from mem"

		# E -> E forwarding
		if mem_state.rd != -1 and mem_state.rd != '00000' and not mem_state.is_dummy:
			if mem_opcode == 3: # load
				if exe_opcode == 35: # store
					if exe_state.rs1 == mem_state.rd and not exe_state.is_dummy:
						data_hazard += 1
						if_stall = True
						stall_position = 0
						gui_pair = {'who': 2, 'from_whom': 1}

				else:
					if (exe_state.rs1 == mem_state.rd or exe_state.rs2 == mem_state.rd) and not exe_state.is_dummy:
						data_hazard += 1
						if_stall = True
						stall_position = 0
						gui_pair = {'who': 2, 'from_whom': 1}

			else:
				if exe_state.rs1 == mem_state.rd and not exe_state.is_dummy:
					exe_state.operand1 = mem_state.register_data
					data_hazard += 1
					gui_pair = {'who': -1, 'from_whom': -1}
					gui_for[2] = "forwarded from execute"

				if exe_state.rs2 == mem_state.rd and not exe_state.is_dummy:
					if exe_opcode != 35: # store
						exe_state.operand2 = mem_state.register_data
					else:
						exe_state.register_data = mem_state.register_data
					data_hazard += 1
					gui_pair = {'who': -1, 'from_whom': -1}
					gui_for[2] = "forwarded from execute"

		if (decode_opcode == 99 or decode_opcode == 103) and not decode_state.is_dummy: # SB and jalr
			# M -> D forwarding
			if wb_state.rd != -1 and wb_state.rd != '00000' and not wb_state.is_dummy:
				if wb_state.rd == decode_state.rs1:
					decode_state.operand1 = wb_state.register_data
					decode_state.decode_forwarding_op1 = True
					data_hazard += 1
					gui_pair = {'who': -1, 'from_whom': -1}
					gui_for[3] = "forwarded from mem"

				if wb_state.rd == decode_state.rs2:
					decode_state.operand2 = wb_state.register_data
					decode_state.decode_forwarding_op2 = True
					data_hazard += 1
					gui_pair = {'who': -1, 'from_whom': -1}
					gui_for[3] = "forwarded from mem"

			# E -> D fowarding
			if mem_state.rd != -1 and mem_state.rd != '00000' and not mem_state.is_dummy:
				if mem_opcode == 3 and (mem_state.rd == decode_state.rs1 or mem_state.rd == decode_state.rs2): # load
					data_hazard += 1
					if_stall = True
					if stall_position > 1:
						stall_position = 1
						gui_pair = {'who': 3, 'from_whom': 1}

				else:
					if mem_state.rd == decode_state.rs1:
						decode_state.operand1 = mem_state.register_data
						decode_state.decode_forwarding_op1 = True
						data_hazard += 1
						gui_pair = {'who': -1, 'from_whom': -1}
						gui_for[3] = "forwarded from execute"

					if mem_state.rd == decode_state.rs2:
						decode_state.operand2 = mem_state.register_data
						decode_state.decode_forwarding_op2 = True
						data_hazard += 1
						gui_pair = {'who': -1, 'from_whom': -1}
						gui_for[3] = "forwarded from execute"

			# If control instruction depends on the previous instruction
			if exe_state.rd != -1 and exe_state.rd != '00000' and (exe_state.rd == decode_state.rs1 or exe_state.rd == decode_state.rs2) and not exe_state.is_dummy:
				data_hazard += 1
				if_stall = True
				if stall_position > 1:
					stall_position = 1
					gui_pair = {'who': 3, 'from_whom': 2}

		gui_pair['from'] = gui_for
		new_states = [wb_state, mem_state, exe_state, decode_state, pipeline_instructions[-1]]
		return [data_hazard, if_stall, stall_position, new_states, gui_pair]
