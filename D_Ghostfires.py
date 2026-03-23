import sys,threading
from collections import defaultdict, Counter, deque
from bisect import bisect_left, bisect_right, insort
import random
import math
from heapq import heapify, heappush, heappop
from random import getrandbits
from itertools import accumulate
from functools import reduce
from operator import add, sub, mul, truediv, floordiv, mod, pow, neg, and_, or_, xor, inv, lshift, rshift
RANDOM = getrandbits(32)
MOD = 10 ** 9 + 7
inf = float('inf')

def solve():
    arr = list(map(int, sys.stdin.readline().split())) 
    arr = [(arr[0],"R"),(arr[1],"G"),(arr[2],"B")]
    cp = arr[:]
    arr.sort(reverse=True)
    cp.sort(reverse=True)
    r,g,b = arr
    r = r[0]
    g = g[0]
    b = b[0]
    s = ''
    def rec(s):
        s = s.upper()
        mp = {"R": cp[0][1],"G":cp[1][1],"B": cp[2][1]}
        res = [mp[c] for c in s]
        return "".join(res)
    if r == 0:
        s = ''
        return rec(s)
    if g == 0:
        s = "R"
        return rec(s)
    elif b == 0:
        s = "RG" * g + ("R" if r > g else '')
        return rec(s)
    ans = []
    while g != b:
        ans.append("rg")
        g -= 1
        r -= 1

    while r and g and b:
        ans.append("rb")
        r -= 1
        b -= 1
        if not r:
            break
        ans.append("rg")
        r -= 1
        g -= 1
    if r:
        s = ''.join(ans).upper()
        return rec(s)
    if b != g:
        ans.append('g')
    for _ in range(b):
        ans.append("bg")
    s = ''.join(ans).upper()
    return rec(s)


    

        
     
    
    
     
    
for _ in range(int(sys.stdin.readline().strip())):  
    s = print(solve())
