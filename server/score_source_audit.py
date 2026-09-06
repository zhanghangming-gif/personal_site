"""Cross-check raster recognition against independent PDF vector geometry."""


def apply_pdf_anchors(analysis, preflight):
    pages = {page['page']: page.get('geometry', {}) for page in preflight.get('pageDetails', [])}
    matched, conflicts, anchors = 0, [], 0
    for system in analysis.get('systems', []):
        geometry = pages.get(system['page'], {})
        staves = geometry.get('staves', [])
        if not staves or not system.get('imageHeight'):
            continue
        sx = system['imageWidth'] / geometry['width']
        sy = system['imageHeight'] / geometry['height']
        nearest = min(staves, key=lambda staff: abs(staff['top']*sy-system['staffTop']))
        spacing = nearest['spacing']
        if abs(nearest['top']*sy-system['staffTop']) > spacing*sy:
            continue
        matched += 1
        system['pdfStaff'] = nearest
        candidates = [number for number in geometry.get('numbers', [])
                      if nearest['left']-5*spacing <= number['x'] <= nearest['left']+2*spacing
                      and nearest['top']-8*spacing <= number['y'] <= nearest['top']-.5*spacing
                      and number['value'] > 0]
        if len(candidates) == 1:
            system['lineStart'] = candidates[0]['value']
            system['lineStartPdf'] = candidates[0]['value']
            anchors += 1
        markers=[]
        for number in geometry.get('numbers', []):
            if (nearest['left'] <= number['x'] <= nearest['right'] and
                    nearest['top']-6*spacing <= number['y'] <= nearest['top']-.5*spacing):
                markers.append({'value':number['value'], 'x':number['x']*sx, 'y':number['y']*sy,
                                'width':number['size']*sx, 'height':number['size']*sy, 'kind':'pdf-text'})
        system['numberMarkers'].extend(markers)
        for index, stack in enumerate(system.get('stacks', [])):
            if stack.get('special') != 'MULTI_REST':
                continue
            # A multirest number is centered in its bar; a rehearsal/bar number
            # near the left boundary must never become a rest duration.
            center=(stack['left']+stack['right'])/2
            counts=[marker for marker in markers if abs(marker['x']-center)<max(12*sx,stack['width']*.16)
                    and 1<marker['value']<=999]
            if len(counts)==1:
                system['restCounts']=[item for item in system.get('restCounts',[]) if item.get('stackIndex')!=index]
                system['restCounts'].append({'stackIndex':index,'value':counts[0]['value'],
                                             'rawValue':counts[0]['value'],'pdfValue':counts[0]['value']})
        # Only complete staves with a closing right bar can prove measure count.
        bars=[x for x in nearest['barlines'] if x>nearest['left']+2*spacing]
        if bars and abs(bars[-1]-nearest['right'])<spacing:
            if len(bars) != system['rawMeasures']:
                conflicts.append({'page':system['page'],'system':system['system'],
                                  'pdfMeasures':len(bars),'recognizedMeasures':system['rawMeasures']})
    recognized=[item['lineStart'] for item in analysis.get('systems',[]) if item.get('lineStart') is not None]
    monotonic=all(b>a for a,b in zip(recognized,recognized[1:]))
    if anchors and monotonic:
        analysis['recognizedLineNumbers']=recognized
        if analysis.get('bookIssue') == '行首小节号识别覆盖不足' and len(recognized)/max(1,len(analysis['systems']))>=.70:
            analysis['bookIssue']=''
    analysis['pdfSourceAudit']={'matchedSystems':matched,'printedAnchors':anchors,'measureConflicts':conflicts}
    return analysis
