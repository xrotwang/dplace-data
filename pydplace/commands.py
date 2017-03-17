# coding: utf8
from __future__ import unicode_literals, print_function, division

import fiona
from shapely.geometry import Point
from ete3 import Tree

from clldutils.clilib import command, ParserError
from clldutils.markup import Table
from clldutils.jsonlib import update

from pydplace import geo
from pydplace import glottolog


@command()
def ls(args):
    t = Table('id', 'name', 'type', 'variables', 'societies')
    for ds in args.repos.datasets:
        t.append([ds.id, ds.name, ds.type, len(ds.variables), len(ds.societies)])
    print(t.render(condensed=False, verbose=True))


@command()
def check(args):
    glottolog = {l.id: l for l in
                 args.repos.read_csv('csv', 'glottolog.csv', namedtuples=True)}

    socids, xdids, varids = set(), set(), set()
    for ds in args.repos.datasets:
        for soc in ds.societies:
            if soc.id in socids:
                args.log.error('duplicate society ID: {0}'.format(soc.id))
            xdids.add(soc.xd_id)
            socids.add(soc.id)
            label = '{0} society {1}'.format(ds.id, soc)
            if soc.glottocode not in glottolog:
                args.log.warn('{0} without valid glottocode {1.glottocode}'.format(
                    label, soc))
            elif glottolog[soc.glottocode].family_name == 'Bookkeeping':
                args.log.warn('{0} mapped to Bookkeeping language: {1.glottocode}'.format(
                    label, soc))
        for var in ds.variables:
            if var.id in varids:
                args.log.error('duplicate variable ID: {0}'.format(var.id))
            varids.add(var.id)

    for p in args.repos.phylogenies:
        for taxon in p.taxa:
            if taxon.glottocode and taxon.glottocode not in glottolog:
                args.log.error('{0}: invalid glottocode {1}'.format(p, taxon.glottocode))
            for socid in taxon.soc_ids:
                if socid not in socids:
                    args.log.error('{0}: invalid soc_id {1}'.format(p, socid))
            for xdid in taxon.xd_ids:
                if xdid not in xdids:
                    args.log.error('{0}: invalid xd_id {1}'.format(p, xdid))
            assert p.nexus

    for t in args.repos.trees:
        assert Tree(t.newick, format=1)


@command(name='glottolog')
def glottolog_(args):
    """Update data derived from Glottolog

    dplace glottolog PATH/TO/GLOTTOLOG/REPOS YEAR VERSION
    """
    if len(args.args) != 3:
        raise ParserError('not enough arguments')
    year, version = args.args[1:3]
    title = "Glottolog {0}".format(version)
    glottolog.update(args.repos, args.args[0], year, title)


@command()
def tdwg(args):
    """
    Assign socities to TDWG regions
    """
    def isclose(a, b, rel_tol=1e-09, abs_tol=0.0):
        return abs(a-b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)

    with fiona.collection(
            args.repos.path("geo", "level2-shape/level2.shp").as_posix(), "r") as source:
        regions = [f for f in source]

    with update(
        args.repos.path("geo", "societies_tdwg.json"), default={}, indent=4
    ) as soc_tdwg:
        for ds in args.repos.datasets:
            for soc in ds.societies:
                spec = soc_tdwg.get(
                    soc.id, dict(lat=soc.Lat, lon=soc.Long, name=None, code=None))
                if isclose(spec['lat'], soc.Lat) \
                        and isclose(spec['lon'], soc.Long) \
                        and spec['code']:
                    continue

                region, dist = geo.match(Point(spec['lon'], spec['lat']), regions)
                spec['name'] = region['properties']['REGION_NAM']
                spec['code'] = region['properties']['TDWG_CODE']

                if dist == 0:
                    args.log.info('{0} contained in region {1}'.format(soc, spec['name']))
                else:
                    args.log.warn(
                        'assigning {0} to nearest region {1}, distance {2}'.format(
                            soc, region['properties']['REGION_NAM'], dist))

                soc_tdwg[soc.id] = spec