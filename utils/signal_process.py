import csv
import numpy as np
import time

def gettimestr():
    return time.strftime('%Y-%m-%d %H_%M_%S', time.localtime(time.time()))

def write_to_csv(fname, data, header=None, row_to_col=True):
    if header is not None:
        for id, col in enumerate(data):
            col.insert(0, header[id])
    with open(fname, 'w', newline='') as csvfile:
        if row_to_col:
            data = np.array(data).transpose()
        csvwriter = csv.writer(csvfile)
        csvwriter.writerows(data)
    return fname