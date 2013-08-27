#!/usr/bin/env python

import os
import sys

def main():

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

# sort and compare the two lists of filenames, note any that don't have a match
# in the other list, and delete them.
  # arr1 = ['a', 'c', 'd']
  # arr2 = ['a', 'b', 'c', 'd']
def matchup(files1, files2):
  missing1 = missing2 = []

  files1.sort()
  files2.sort()
  len1 = len(files1)
  len2 = len(files2)
  i = j = 0
  while i < len1 and j < len2:
    sys.stdout.write(str(i)+" "+str(j))
    if files1[i] == files2[j]:
      print " - matched up"
      i+=1
      j+=1
      continue
    else:
      print " - not matched"
      a = i
      b = j
      i_end = i
      j_end = j
      skipped1 = { files1[a]:a }
      skipped2 = { files2[b]:b }
      found_it = False;
      # find the first file on either side that matches, load up the dict's
      while not found_it and a < len1 and b < len2:
        skipped1[files1[a]] = a
        skipped2[files2[b]] = b
        if files1[a] in skipped2:
          found_it = True
          print "found "+files1[a]+" in arr2"
          i_end = a
          j_end = skipped2[files1[a]]
        else:
          a+=1
        if files2[b] in skipped1:
          found_it = True
          print "found "+files2[b]+" in arr1, index "+str(b)+" in arr2"
          j_end = b
          i_end = skipped1[files2[b]]
        else:
          b+=1
      # TODO handle case where the matches aren't found
      # then start again at i and j, and add each file to missing until you
      # hit the first one that's present in the other's skipped
      i_tmp = i
      j_tmp = j
      i_delete = i_end - i
      j_delete = j_end - j
      while i_tmp < i_end:
        missing1.append(files1[i_tmp])
        del(files1[i_tmp])
        len1 = len(files1)
        i+=1
      while j_tmp < j_end:
        missing2.append(files2[j_tmp])
        del(files2[j_tmp])
        len2 = len(files2)
        j_tmp+=1
  
  return (missing1, missing2)



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

if __name__ == "__main__":
  main()