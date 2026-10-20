"""Mechanics checks only; passing tests do not establish real-fabric accuracy."""
import numpy as np
from .common import decision
from .connections import transformed
from .graph import connect,score_same_only
from .reconstruction import fragments,sparse_crossings,direction
from .weave import match,templates


def seg(i,a,b):return {'id':str(i),'points':[a,b],'family':None}


def test_decoder_does_not_invent_class_zero():
    assert decision(np.array([[[.2,.4,.4],[.8,.1,.1]]])).tolist()==[[3,0]]


def test_assignment_endpoint_capacity_and_rotation_scale():
    s=[seg(1,[0,0],[10,0]),seg(2,[16,0],[26,0]),seg(3,[32,0],[42,0]),seg(4,[16,2],[26,2])]
    base=connect(s);edges={tuple(sorted(p)) for p in base['edges']}
    assert base['branching_nodes']==0
    assert len({a for a,b in base['edges']})==len(base['edges'])
    assert len({b for a,b in base['edges']})==len(base['edges'])
    for degree,scale in ((45,1),(90,1),(180,1),(0,2)):
        q=connect(transformed(s,degree,scale));assert {tuple(sorted(p)) for p in q['edges']}==edges


def test_no_relations_enter_prediction_and_no_unlabelled_negatives():
    s=[seg(1,[0,0],[10,0]),seg(2,[16,0],[26,0])];r=connect(s)
    a=score_same_only(s,r,[]);b=score_same_only(s,r,[{'a':'1','b':'2','relation':'SAME_PHYSICAL_YARN'}])
    assert a['precision'] is None and b['precision'] is None
    assert a['same_pair_recall_weak'] is None and b['same_pair_recall_weak']==1
    assert r==connect(s)


def test_local_rules_do_not_depend_on_arbitrary_axis_sign():
    s=[seg(1,[0,0],[10,0]),seg(2,[16,0],[26,0]),seg(3,[16,2],[26,2])]
    for method in ('axis_nearest','local_tangent'):
        base={tuple(sorted(e)) for e in connect(s,method)['edges']}
        rotated_segments=[{**item,'points':(-np.asarray(item['points'])).tolist()} for item in s]
        rotated={tuple(sorted(e)) for e in connect(rotated_segments,method)['edges']}
        assert base==rotated


def test_no_unknown_pixels_become_regions():
    labels=np.full((80,80),3,np.uint8);s,inst,reject=fragments(labels)
    assert s==[] and np.count_nonzero(inst)==0


def test_region_centerline_has_image_support_and_contour():
    labels=np.full((80,80),3,np.uint8);labels[10:70,20:28]=0
    s,inst,reject=fragments(labels);assert len(s)==1 and s[0]['contours']
    for point in s[0]['points']:
        x,y=np.rint(point).astype(int);assert inst[y,x]==1


def test_no_visible_inferred_crossing_without_both_families():
    labels=np.full((80,80),3,np.uint8);labels[10:70,20:28]=0
    s,inst,_=fragments(labels);r=connect(s);dirs={'A':direction(s),'B':None}
    matrix,cells,paths,byfamily=sparse_crossings(s,inst,r,dirs)
    assert matrix.size==0 and cells==[]


def test_crossing_requires_visible_pixel_support_not_only_lines():
    s=[{**seg(1,[20,5],[20,15]),'family':'A'},
       {**seg(2,[20,25],[20,35]),'family':'A'},
       {**seg(3,[5,20],[35,20]),'family':'B'}]
    inst=np.zeros((40,40),np.int32);inst[5:16,18:23]=1;inst[25:36,18:23]=2;inst[18:23,5:36]=3
    graph=connect(s);dirs={f:direction([q for q in s if q['family']==f]) for f in ('A','B')}
    matrix,cells,*_=sparse_crossings(s,inst,graph,dirs)
    assert len(cells)==1 and matrix[0,0]==0
    inst[inst==3]=0
    matrix,cells,*_=sparse_crossings(s,inst,graph,dirs)
    assert not cells and (matrix==-1).all()


def test_templates_small_unknown_and_one_sided_abstain():
    assert match(np.full((8,8),-1))['coarse_candidate'] is None
    assert match(np.zeros((5,8)))['coarse_candidate'] is None
    assert match(np.zeros((8,8)))['status']=='ONE_SIDED_EVIDENCE'


def test_template_phase_complement_and_sparse_support():
    done=set()
    for name,coarse,params,grid in templates((20,20)):
        m=grid.copy();m[::3,::3]=-1
        result=match(m)
        assert result['coarse_candidate']==coarse,(name,result)
        assert result['observed_cells']==int((m>=0).sum())
        assert result['physical_weave_verified'] is False
        assert result['index_continuity_verified'] is False
        done.add(name)
    assert len(done)==9
