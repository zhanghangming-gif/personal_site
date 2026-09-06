"""Read vector staff geometry and printed numeric anchors without OMR.

Unknown drawing styles return no geometry. Nothing here depends on the score
title, PDF digest, a music-font encoding or coordinates from another document.
"""
import math
import re
from pypdf.generic import ContentStream


def multiply(a, b):
    return [a[0]*b[0]+a[1]*b[2], a[0]*b[1]+a[1]*b[3],
            a[2]*b[0]+a[3]*b[2], a[2]*b[1]+a[3]*b[3],
            a[4]*b[0]+a[5]*b[2]+b[4], a[4]*b[1]+a[5]*b[3]+b[5]]


def point(matrix, x, y):
    return x*matrix[0]+y*matrix[2]+matrix[4], x*matrix[1]+y*matrix[3]+matrix[5]


def page_geometry(page, reader):
    if page.rotation % 360:
        return {'supported': False, 'reason': 'rotated_page', 'staves': [], 'numbers': []}
    width, height = float(page.mediabox.width), float(page.mediabox.height)
    horizontal, vertical = [], []

    def paths(stream, resources, initial=(1, 0, 0, 1, 0, 0), depth=0):
        if depth > 8:
            return
        resources = resources.get_object() if hasattr(resources, 'get_object') else resources
        matrix, stack, segments, current = list(initial), [], [], None
        for operands, operator in ContentStream(stream, reader).operations:
            if operator == b'q':
                stack.append(list(matrix))
            elif operator == b'Q' and stack:
                matrix = stack.pop()
            elif operator == b'cm':
                matrix = multiply(list(map(float, operands)), matrix)
            elif operator == b'm':
                current = point(matrix, *map(float, operands))
            elif operator == b'l':
                end = point(matrix, *map(float, operands))
                if current:
                    segments.append((current, end))
                current = end
            elif operator == b're':
                x, y, w, h = map(float, operands)
                vertices = [point(matrix, px, py) for px, py in ((x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y))]
                segments.extend(zip(vertices, vertices[1:]))
            elif operator in (b'c', b'v', b'y'):
                current = point(matrix, float(operands[-2]), float(operands[-1]))
            elif operator in (b'S', b's', b'B', b'B*', b'b', b'b*', b'f', b'f*', b'F', b'n'):
                if operator not in (b'n',):
                    for (x1,y1), (x2,y2) in segments:
                        if abs(y1-y2) < .2 and abs(x1-x2) > 20:
                            horizontal.append((min(x1,x2), max(x1,x2), height-(y1+y2)/2))
                        elif abs(x1-x2) < .2 and abs(y1-y2) > 5:
                            vertical.append(((x1+x2)/2, height-max(y1,y2), height-min(y1,y2)))
                segments, current = [], None
            elif operator == b'Do':
                objects = resources.get('/XObject', {})
                objects = objects.get_object() if hasattr(objects, 'get_object') else objects
                obj = objects.get(operands[0])
                if obj:
                    obj = obj.get_object()
                    if obj.get('/Subtype') == '/Form':
                        paths(obj, obj.get('/Resources', resources), multiply(list(map(float,obj.get('/Matrix',[1,0,0,1,0,0]))),matrix),depth+1)

    paths(page.get_contents(), page.get('/Resources', {}))
    # Engravers may emit one staff-line segment per measure.
    rows={}
    for left,right,y in horizontal:
        bucket=round(y,1)
        rows.setdefault(bucket,[]).append((left,right))
    horizontal=[]
    for y,segments in rows.items():
        merged=[]
        for left,right in sorted(segments):
            if merged and left<=merged[-1][1]+2:
                merged[-1]=(merged[-1][0],max(right,merged[-1][1]))
            else:
                merged.append((left,right))
        horizontal.extend((left,right,y) for left,right in merged if right-left>width*.22)
    horizontal = sorted(set(tuple(round(v,2) for v in row) for row in horizontal), key=lambda row:row[2])
    used, staves = set(), []
    for index, (left,right,top) in enumerate(horizontal):
        if index in used:
            continue
        aligned = [(i,y) for i,(x1,x2,y) in enumerate(horizontal)
                   if i not in used and y >= top and abs(x1-left)<1 and abs(x2-right)<1 and y-top<=60]
        if len(aligned)<5:
            continue
        five = aligned[:5]
        gaps = [b[1]-a[1] for a,b in zip(five,five[1:])]
        if min(gaps)<1.5 or max(gaps)>15 or max(gaps)-min(gaps)>.3:
            continue
        used.update(i for i,_ in five)
        bottom = five[-1][1]
        spacing = (bottom-top)/4
        bars = sorted(set(round(x,1) for x,y1,y2 in vertical
                          if left-.5<=x<=right+.5 and abs(y1-top)<=.8 and abs(y2-bottom)<=.8))
        # Keep double barlines as a single boundary.
        boundaries=[]
        for x in bars:
            if not boundaries or x-boundaries[-1]>spacing*1.4:
                boundaries.append(x)
        staves.append({'left':left,'right':right,'top':top,'bottom':bottom,'spacing':round(spacing,3),'barlines':boundaries})
    numbers=[]
    def visit(text, cm, tm, font, size):
        if not re.fullmatch(r'\s*\d{1,4}\s*',text):
            return
        descriptor=font.get('/FontDescriptor',{}) if font else {}
        descriptor=descriptor.get_object() if hasattr(descriptor,'get_object') else descriptor
        if int(descriptor.get('/Flags',0)) & 4:
            return
        matrix=multiply(tm,cm)
        x,y=point(matrix,0,0)
        numbers.append({'value':int(text.strip()),'x':round(x,3),'y':round(height-y,3),
                        'size':round(size*math.hypot(matrix[0],matrix[1]),3)})
    page.extract_text(visitor_text=visit)
    return {'supported':bool(staves),'staves':staves,'numbers':numbers,
            'width':width,'height':height}
