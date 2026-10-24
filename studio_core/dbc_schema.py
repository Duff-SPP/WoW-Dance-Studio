"""Explicit WDBC 12340 layouts. No retail DB2 inference or editor dependency.

Column facts cross-checked with WDBX d34cee1 build 12340 and TrinityCore 335.
Raw integer words retain their bits; signed views are available separately.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Schema:
    name: str
    fields: tuple
    strings: tuple = ()
    floats: tuple = ()

    @property
    def size(self): return len(self.fields)*4


def numbered(prefix,count): return tuple(prefix+str(i) for i in range(count))


SCHEMAS={}
def table(name,fields,strings=(),floats=()):
    SCHEMAS[name]=Schema(name,tuple(fields),tuple(strings),tuple(floats))

table('AnimationData',('ID','Name','Weaponflags','Bodyflags','Flags','Fallback','BehaviorID','BehaviorTier'),(1,))
table('Emotes',('ID','EmoteSlashCommand','AnimID','EmoteFlags','EmoteSpecProc','EmoteSpecProcParam','EventSoundID'),(1,))
table('SoundEntries',('ID','SoundType','Name')+numbered('File',10)+numbered('Freq',10)+
      ('DirectoryBase','Volume','Flags','MinDistance','DistanceCutoff','EAXDef','AdvancedID'),
      (2,*range(3,13),23),(24,26,27))
table('EmotesText',('ID','Name','EmoteID')+numbered('EmoteText',16),(1,))
table('EmotesTextData',('ID',)+numbered('TextLang',16)+('LocaleFlags',),range(1,17))
table('EmotesTextSound',('ID','EmotesTextID','RaceID','SexID','SoundID'))
table('DanceMoves',('ID','Type','Param','Fallback','RaceMask','InternalName')+numbered('NameLang',16)+('LocaleFlags','LockID'),(5,*range(6,22)))
table('SoundEntriesAdvanced',('ID','SoundEntryID','InnerRadius2D','TimeA','TimeB','TimeC','TimeD','RandomOffsetRange','Usage',
      'TimeIntervalMin','TimeIntervalMax','VolumeSliderCategory','DuckToSFX','DuckToMusic','DuckToAmbience',
      'InnerRadiusOfInfluence','OuterRadiusOfInfluence','TimeToDuck','TimeToUnduck','InsideAngle','OutsideAngle',
      'OutsideVolume','OuterRadius2D','Name'),(23,),(2,12,13,14,15,16,19,20,21,22))
table('ChrRaces',('ID','Flags','FactionID','ExplorationSoundID','MaleDisplayID','FemaleDisplayID','ClientPrefix',
      'BaseLanguage','CreatureType','ResSicknessSpellID','SplashSoundID','ClientFileString','CinematicSequenceID','Alliance')+
      numbered('NameLang',16)+('NameLangFlags',)+numbered('FemaleLang',16)+('FemaleLangFlags',)+
      numbered('MaleLang',16)+('MaleLangFlags',)+('FacialHair0','FacialHair1','HairCustomization','Expansion'),
      (6,11,*range(14,30),*range(31,47),*range(48,64),65,66,67))
table('CreatureDisplayInfo',('ID','ModelID','SoundID','ExtendedDisplayID','Scale','Alpha','Texture0','Texture1','Texture2',
      'Portrait','BloodLevel','BloodID','NPCSoundID','ParticleColorID','GeosetData','ObjectEffectPackageID'),(6,7,8,9),(4,))
table('CreatureModelData',('ID','Flags','ModelName','SizeClass','Scale','BloodID','FootprintTextureID','FootprintLength',
      'FootprintWidth','FootprintParticleScale','FoleyMaterialID','FootstepShakeSize','DeathThudShakeSize','SoundID',
      'CollisionWidth','CollisionHeight','MountHeight','BoxMinX','BoxMinY','BoxMinZ','BoxMaxX','BoxMaxY','BoxMaxZ',
      'WorldEffectScale','AttachedEffectScale','MissileRadius','MissilePush','MissileRaise'),(2,),
      (4,7,8,9,*range(14,28)))

# Only references whose meaning is established for this build and supplied tables.
REFERENCES={
    'AnimationData':((5,'AnimationData',True),(6,'AnimationData',True)),
    'Emotes':((2,'AnimationData',False),(6,'SoundEntries',True)),
    'SoundEntries':((29,'SoundEntriesAdvanced',True),),
    'EmotesText':((2,'Emotes',True),*((i,'EmotesTextData',True) for i in range(3,19))),
    'EmotesTextSound':((1,'EmotesText',False),(2,'ChrRaces',False),(4,'SoundEntries',False)),
    'SoundEntriesAdvanced':((1,'SoundEntries',True),),
    'ChrRaces':((4,'CreatureDisplayInfo',True),(5,'CreatureDisplayInfo',True)),
    'CreatureDisplayInfo':((1,'CreatureModelData',False),),
}
PRIMARY=('AnimationData','Emotes','SoundEntries')
