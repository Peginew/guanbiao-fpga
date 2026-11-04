"""Annotation assembly only. Never trains, changes source images, or accesses a board.

The geometric proposals are reviewed on the recorded per-image crop sheets.
Unknown / occluded points are withheld rather than reconstructed from pressure.
"""
from pathlib import Path
import json, hashlib, math
from collections import Counter
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
INVENTORY = HERE.parent / 'inventory_review' / 'inventory.json'


def point(xy=None, visibility='unknown', uncertainty=None, method=None):
    p = {'visibility': visibility, 'xy': xy}
    if xy is not None:
        p['uncertainty_px'] = uncertainty
    if method:
        p['annotation_method'] = method
    return p


def main():
    proposals = json.loads((HERE / 'point_proposals.json').read_text(encoding='utf-8'))
    inv = {x['path']: x for x in json.loads(INVENTORY.read_text(encoding='utf-8'))['images']}
    records = []
    # These overrides come from direct inspection of the complete native frame.
    # Visible extent is used where a gauge extends past the image boundary.
    extras = {
        'D_052': [95, 0, 1180, 720], 'D_053': [515, 218, 635, 355],
        'D_054': [336, 225, 572, 454], 'D_055': [302, 240, 526, 465],
        'E_050': [0, 0, 1010, 720], 'E_051': [478, 120, 610, 260],
        'E_052': [459, 326, 780, 647], 'E_053': [432, 332, 718, 627],
        'F_026': [235, 358, 695, 720], 'F_052': [130, 0, 1020, 720],
        'F_053': [360, 225, 565, 410],
        'F_054': [328, 220, 572, 478], 'F_055': [275, 220, 539, 469],
    }
    no_face = {'D_049': 'empty_scene', 'D_050': 'circular_non_gauge_ball', 'D_051': 'gauge_backside',
               'E_047': 'empty_scene', 'E_048': 'circular_non_gauge_ball', 'E_049': 'gauge_backside',
               'F_049': 'empty_scene', 'F_050': 'circular_non_gauge_ball', 'F_051': 'gauge_backside'}
    hub_occluded = {'D_056', 'D_057', 'E_054', 'E_055', 'F_056', 'F_057'}
    tip_occluded = {'D_058', 'D_059', 'E_056', 'E_057', 'F_058', 'F_059'}
    # The ray peak is wrong when an occluder or strong white reflection dominates.
    tip_withheld = {'D_034', 'E_004', 'F_003', 'F_009', 'F_015', 'F_021',
                    'F_027', 'F_029', 'F_045'}
    # Manual tip correction in canonical *image* coordinates is not pressure inversion.
    # The remaining coordinates retain their proposal precision / uncertainty.
    manual_angle = {'F_029': 225}
    for a in proposals:
        ident = a['id']; g, nstr = ident.split('_'); n = int(nstr)
        src = inv[a['path']]
        record = {
            'id': ident, 'session_id': g, 'path': a['path'], 'image_path': a['path'],
            'sha256': src['sha256'], 'width': 1280, 'height': 720,
            'input_kind': 'native_bgr1280x720', 'label_coordinates': 'native',
            'split': 'unassigned', 'independent_reposition': None,
            'label_method': 'AI_VISUAL_REVIEWED_GEOMETRY_ASSISTED_NO_PRESSURE_INVERSION',
            'review_status': 'ai_visual_reviewed_not_independent_human_ground_truth',
            'review_pages': [f'{g}_contact_{(n-1)//20+1}.jpg', f'{g}_points_{(n-1)//20+1}.jpg'],
            'bbox_native_xyxy': None, 'bbox_convention': 'half_open_xyxy_visible_extent',
            'keypoints': {'hub': point(), 'thin_terminal': point()},
            'pressure_raw_value': None, 'pressure_raw_unit': 'psi',
            'pressure_label_source': None, 'pressure_rank_descending': None,
            'condition_slot': None, 'condition': 'unknown',
            'annotation_notes': [],
        }
        if ident in no_face:
            record.update(image_kind='absent', negative_kind=no_face[ident], condition=no_face[ident])
            record['keypoints'] = {'hub': point(visibility='absent'), 'thin_terminal': point(visibility='absent')}
            record['annotation_notes'].append('No front dial face; backside is retained as a separate hard-negative category.')
            records.append(record); continue
        record['image_kind'] = 'readable_gauge'
        bbox = extras.get(ident, a['bbox_proposal'])
        if bbox and 55 < bbox[2]-bbox[0] < 1500 and 55 < bbox[3]-bbox[1] < 1000:
            record['bbox_native_xyxy'] = [max(0, int(math.floor(bbox[0]))), max(0, int(math.floor(bbox[1]))),
                                         min(1280, int(math.ceil(bbox[2]))), min(720, int(math.ceil(bbox[3])))]
            record['bbox_uncertainty_px'] = 8 if ident not in extras else 12
        record['geometry_proposal'] = {
            'method': 'SIFT_print_homography_plus_gray_ray_CONSIDERED_PROPOSAL_ONLY',
            'reference_id': 'D_001', 'reference_hub_native': [490, 252],
            'inliers': a['inliers'], 'hub_xy': a['hub_proposal'],
            'thin_terminal_xy': a.get('needle_proposal'),
            'pressure_used_for_geometry': False,
        }
        if a['hub_proposal'] is not None and a['inliers'] >= 8:
            hub = [round(float(x), 1) for x in a['hub_proposal']]
            uncertainty = 4 if a['inliers'] >= 35 and g != 'F' else 7
            record['keypoints']['hub'] = point(hub, 'visible', uncertainty, 'AI_visual_review_of_print_registration_proposal')
            if 'needle_angle_proposal' in a:
                # Measured needle length of the same physical gauge is used only
                # as a geometric endpoint proposal; no bar-to-angle mapping exists.
                theta = math.radians(manual_angle.get(ident, a['needle_angle_proposal']))
                canonical = np.float32([[[490 + 105*math.cos(theta), 252 + 105*math.sin(theta)]]])
                xy = cv2.perspectiveTransform(canonical, np.array(a['H']))[0,0]
                if np.isfinite(xy).all():
                    record['keypoints']['thin_terminal'] = point([round(float(x),1) for x in xy], 'visible',
                        5 if a['inliers'] >= 35 and g != 'F' else 8,
                        'AI_visual_review_of_native_gray_needle_direction_and_same_gauge_endpoint_proposal')
        if ident in extras:
            record['image_kind'] = 'unreadable_gauge'
            record['condition'] = ('partial_or_oversized' if ident.endswith('052') and g != 'E'
                                   or ident in {'E_050', 'F_026'} else 'small_or_severe_lighting')
            record['annotation_notes'].append('Native-frame visible extent directly reviewed; unresolved fine points deliberately UNKNOWN.')
            record['keypoints'] = {'hub': point(), 'thin_terminal': point()}
        if ident in hub_occluded:
            record['image_kind']='unreadable_gauge'; record['condition']='hub_occluded'
            record['keypoints']['hub'] = point(visibility='occluded')
        if ident in tip_occluded:
            record['image_kind']='unreadable_gauge'; record['condition']='thin_terminal_occluded'
            record['keypoints']['thin_terminal'] = point(visibility='occluded')
        if ident in tip_withheld:
            record['keypoints']['thin_terminal'] = point()
            record['annotation_notes'].append('Needle endpoint uncertain under dark/glare/oblique evidence; not promoted from an algorithm proposal.')
        # Establish intended eight pressure slots only for the main capture sequence.
        original = n if g != 'E' else (n if n <= 23 else n+1 if n <= 41 else n+2 if n <= 46 else None)
        if original is not None and 1 <= original <= 48:
            rank = (original-1)//6+1; slot = (original-1)%6+1
            levels = [12,11.5,10,8.5,7,5.5,4,2.5] if g == 'F' else [12,11,9.5,8,6.5,5,3.5,2.5]
            record.update(pressure_raw_value=levels[rank-1], pressure_rank_descending=rank, condition_slot=slot,
                          pressure_label_source='USER_REPORTED_SESSION_PRESSURE_LIST_AND_CAPTURE_ORDER_NOT_INFERRED_FROM_PIXELS')
            if record['condition']=='unknown':
                record['condition'] = ['front_standard','front_larger','dim','backlit','oblique_left','oblique_right'][slot-1]
        if ident in {'E_058','E_059'}:
            val,rank,slot = (8,4,6) if ident=='E_058' else (2.5,8,1)
            record.update(pressure_raw_value=val,pressure_rank_descending=rank,condition_slot=slot,
                          pressure_label_source='USER_FILENAME_EXPLICIT_PSI_AND_CAPTURE_CONFIRMATION',
                          condition='oblique_right' if ident=='E_058' else 'front_standard',supplement=True)
        if (g in {'D','F'} and 52 <= n <= 59) or (g=='E' and 50 <= n <= 57):
            record.update(pressure_raw_value=2.5,pressure_rank_descending=8,
                          pressure_label_source='USER_EXPLICIT_CHALLENGE_PRESSURE_CONFIRMATION')
        if record['keypoints']['hub']['visibility']!='visible' or record['keypoints']['thin_terminal']['visibility']!='visible':
            record['readable_for_joint_keypoint_supervision']=False
        else:
            record['readable_for_joint_keypoint_supervision']=True
        record['pressure_reference_is_user_reported_not_calibrated_measurement'] = True
        records.append(record)
    doc={'schema':'meter_annotation_review_v1','coordinate_system':'native1280x720_top_left_xy',
         'scope':'D/E/F only; annotation not training', 'original_images_modified':False,
         'training_performed':False,'records':records,
         'limits':['AI visual reviewed semi-automatic proposals are not independent human ground truth.',
                   'SIFT uses only this NEW dataset D_001; no historical images, old CNN labels, bar inversion, or FPGA OSD coordinates used.',
                   'Gauge rim is a visible extent box; partially clipped full-object/amodal boxes are not invented.',
                   'Main pressure order comes from user lists; later supplement timestamp is not treated as low pressure.',
                   'Single circular non-gauge instance per group; former second circular distractor coverage is absent.',
                   'No train/dev/test assignment or independent session claim is made.']}
    (HERE/'annotation.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary={'records':len(records),'image_kind':dict(Counter(r['image_kind'] for r in records)),
             'visible_hubs':sum(r['keypoints']['hub']['visibility']=='visible' for r in records),
             'visible_thin_terminals':sum(r['keypoints']['thin_terminal']['visibility']=='visible' for r in records),
             'full_visible_pairs':sum(r.get('readable_for_joint_keypoint_supervision',False) for r in records),
             'known_pressure':sum(r['pressure_raw_value'] is not None for r in records),
             'training_performed':False,'raw_images_modified':False,
             'annotation_sha256':hashlib.sha256((HERE/'annotation.json').read_bytes()).hexdigest()}
    (HERE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
