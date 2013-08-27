#!/usr/bin/env python

import os
import sys

def main():
  test_matchup()
  sys.exit(0)
  arr1 = ['a', 'c', 'd']
  arr2 = ['a', 'b', 'c', 'd']
  (missing1, missing2) = matchup(arr1, arr2)
  print "arr1: "+str(arr1)
  print "arr2: "+str(arr2)
  print "missing1: "+str(missing1)
  print "missing2: "+str(missing2)
  sys.exit(0)

  rootdir1 = ''
  rootdir2 = ''
  if len(sys.argv) > 2:
    rootdir1 = sys.argv[1]
    rootdir2 = sys.argv[2]

  (size1, files1, dirs1) = totalsize(rootdir1)
  (size2, files2, dirs2) = totalsize(rootdir2)
  if size1 == size2 and files1 == files2 and dirs1 == dirs2:
    print (rootdir1+" is the same size as "+rootdir2+" and has the same number "
      +"of files and directories.")
    sys.exit(0)
  else:
    print (rootdir1+": "+str(size1)+" bytes, "+str(files1)+" files, "+str(dirs1)
      +" directories")
    print (rootdir2+": "+str(size2)+" bytes, "+str(files2)+" files, "+str(dirs2)
      +" directories")
    # sys.exit(0)

  walker1 = os.walk(rootdir1)
  walker2 = os.walk(rootdir2)
  done1 = done2 = False
  todo1 = todo2 = []
  (dir1, dirnames1, filenames1) = walker1.next()
  (dir2, dirnames2, filenames2) = walker2.next()
  while not done1 and not done2:
    # make sure walker visits the directories in the same order
    # the order of the directories in dirnames will be the order the walker
    # visits them.

    # TODO: double-check that functions pass by reference.
    (missing1, missing2) = matchup(dirnames1, dirnames2)

    # <s>sync up the lists</s>
    # scratch that. detecting different CONTENTS isn't done by comparing dir1
    # and dir2. it's by comparing dirnames and filenames. so to prevent
    # dir1 != dir2, just compare dirnames1 and dirnames2 each time. sync THOSE
    # lists, and del() any dirnames without a counterpart.

    print dir1+"\t"+dir2
    try:
      (dir1,dirnames1,filenames1) = walker1.next()
    except StopIteration, si:
      done1 = True
    try:
      (dir2,dirnames2,filenames2) = walker2.next()
    except StopIteration, si:
      done2 = True


##### FUNCTIONS #####

def totalsize(root_dir):
  size = 0
  files = 0
  dirs = 0
  for dirpath, dirnames, filenames in os.walk(root_dir):
    files += len(filenames)
    dirs += len(dirnames)
    for filename in filenames:
      filepath = os.path.join(dirpath, filename)
      size += os.path.getsize(filepath)
  return (size, files, dirs)

# sort and compare the two lists of filenames, note any that don't have a match
# in the other list, and delete them.
  # arr1 = ['a', 'c', 'd']
  # arr2 = ['a', 'b', 'c', 'd']
def matchup(files1, files2):
  missing1 = []
  missing2 = []

  files1.sort()
  files2.sort()
  len1 = len(files1)
  len2 = len(files2)
  i = j = 0
  while i < len1 and j < len2:
    if files1[i] == files2[j]:
      print (str(i)+":"+files1[i]+" "+str(j)+":"+files2[j]
        +" - matched up")
      i+=1
      j+=1
      continue
    else:
      print "mismatch:"
      a = i
      b = j
      i_end = i
      j_end = j
      skipped1 = { files1[a]:a }
      skipped2 = { files2[b]:b }
      found_it = False;
      # find the first file on either side that matches, load up the dict's
      while not found_it and not (a >= len1 and b >= len2):
        print "\t"+str(a)+":"+files1[a]+" "+str(b)+":"+files2[b]
        skipped1[files1[a]] = a
        skipped2[files2[b]] = b
        if files1[a] in skipped2:
          found_it = True
          print "found "+files1[a]+" in arr2, index "+str(a)+" in arr1"
          i_end = a
          j_end = skipped2[files1[a]]
        elif a < len1 - 1:
          a+=1
        if files2[b] in skipped1:
          found_it = True
          print "found "+files2[b]+" in arr1, index "+str(b)+" in arr2"
          j_end = b
          i_end = skipped1[files2[b]]
        elif b < len2 - 1:
          b+=1
      # TODO handle case where the matches aren't found.

      # then start again at i and j, and add each file to missing until you
      # hit the first one that's present in the other's skipped
      i_tmp = i
      j_tmp = j
      print ("deleting everything from ["+str(i_tmp)+" to "
        +str(i_end-1)+"] from arr1")
      print ("                     and ["+str(j_tmp)+" to "
        +str(j_end-1)+"] from arr2")
      while i_tmp < i_end:
        print "adding "+str(i)+":"+files1[i]+" from files1 to missing1"
        missing1.append(files1[i])
        del(files1[i])
        len1 = len(files1)
        i_tmp+=1
      while j_tmp < j_end:
        print "adding "+str(j)+":"+files2[j]+" from files2 to missing2"
        missing2.append(files2[j])
        del(files2[j])
        len2 = len(files2)
        j_tmp+=1

  # Check for extra files at the end of one list that aren't present in the
  # other. The above algorithm needs missing files to be flanked by matching
  # ones. If there's a run of missing files at the end with no matching one
  # following the run, they won't be caught above.
  if len1 < len2:
    j_tmp = len1
    j_end = len2
    while j_tmp < j_end:
      missing2.append(files2[len1])
      del(files2[len1])
      j_tmp+=1
    len2 = len(files2)
  elif len2 < len1:
    i_tmp = len2
    i_end = len1
    while i_tmp < i_end:
      missing1.append(files1[len2])
      del(files1[len2])
      i_tmp+=1
    len1 = len(files1)

  return (missing1, missing2)

def test_matchup():
  failures = 0;
  inputs = [
    [ ['a', 'b', 'c'],            #0
      ['a', 'b', 'c'],          ],
    [ ['a', 'c', 'd'],            #1
      ['a', 'b', 'c', 'd'],     ],
    [ ['a', 'b', 'c', 'd'],       #2
      ['a', 'd'],               ],
    [ ['a', 'b', 'c', 'd', 'e', 'f'], #3
      ['a', 'd', 'f'],          ],
    [ ['a', 'b', 'c', 'd', 'f'],  #4
      ['a', 'd', 'e', 'f'],     ],
    [ ['a', 'd', 'e'],            #5
      ['a', 'b', 'c', 'e'],     ],
    [ ['a', 'd', 'e', 'f'],       #6
      ['a', 'b', 'c', 'e', 'f'],],
    [ ['a', 'b', 'c'],            #7
      ['b', 'c'],               ],
    [ ['a', 'b', 'c'],            #8
      ['a', 'b'],               ],
    [ ['a', 'b'],                 #9
      ['b', 'c'],               ],
    [ ['a', 'b', 'c', 'e', 'f', 'g'], #10
      ['a', 'b', 'd', 'e'],     ],
    [ ['a', 'b', 'c'],            #11
      ['a', 'd', 'e'],          ],
    [ ['a', 'b', 'c'],            #12
      ['d', 'e', 'f'],          ],
    [ ['a', 'b', 'c', 'd'],       #13
      ['a', 'e', 'f'],          ],
  ]
  outputs = [
    # 0: output arr1   1: missing1
    # 2: output arr2   3: missing2 
    [ ['a', 'b', 'c'], [],        #0
      ['a', 'b', 'c'], [],      ],
    [ ['a', 'c', 'd'], [],        #1
      ['a', 'c', 'd'], ['b'],   ],
    [ ['a', 'd'], ['b', 'c'],     #2
      ['a', 'd'], [],           ],
    [ ['a', 'd', 'f'], ['b', 'c', 'e'], #3
      ['a', 'd', 'f'], [],      ],
    [ ['a', 'd', 'f'], ['b', 'c'],#4
      ['a', 'd', 'f'], ['e'],   ],
    [ ['a', 'e'], ['d'],          #5
      ['a', 'e'], ['b', 'c'],   ],
    [ ['a', 'e', 'f'], ['d'],     #6
      ['a', 'e', 'f'], ['b', 'c'],  ],
    [ ['b', 'c'], ['a'],          #7
      ['b', 'c'], [],           ],
    [ ['a', 'b'], ['c'],          #8
      ['a', 'b'], [],           ],
    [ ['b'], ['a'],               #9
      ['b'], ['c'],             ],
    [ ['a', 'b', 'e'], ['c', 'f', 'g'], #10
      ['a', 'b', 'e'], ['d'],   ],
    [ ['a'], ['b', 'c'],          #11
      ['a'], ['d', 'e'],        ],
    [ [], ['a', 'b', 'c'],        #12
      [], ['d', 'e', 'f'],      ],
    [ ['a'], ['b', 'c', 'd'],     #13
      ['a'], ['d', 'e'],        ],
  ]

  for inout_pair in zip(inputs, outputs):
    inputt = inout_pair[0]
    output = inout_pair[1]
    print "starting: "+str(inputt[0])
    print "      and "+str(inputt[1])
    (missing1, missing2) = matchup(inputt[0], inputt[1])
    print "missing1: "+str(missing1)
    print "missing2: "+str(missing2)
    print "modified arr1: "+str(inputt[0])
    print "modified arr2: "+str(inputt[1])
    if (missing1 == output[1] and missing2 == output[3] and
      inputt[0] == output[0] and inputt[1] == output[2]):
      print "output match"
    else:
      failures+=1;
      print "\tNo output match! Actual/Expected:"
      print "missing1: "+str(missing1)
      print "expected: "+str(output[1])
      print "missing2: "+str(missing2)
      print "expected: "+str(output[3])
      print "new arr1: "+str(inputt[0])
      print "expected: "+str(output[0])
      print "new arr2: "+str(inputt[1])
      print "expected: "+str(output[2])
    print ""

  if failures:
    print "did not pass! "+str(failures)+" failures."
  else:
    print "passed all tests!"

if __name__ == "__main__":
  main()