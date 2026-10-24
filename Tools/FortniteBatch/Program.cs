using System;
using System.IO;
using System.Threading.Tasks;
using System.Collections.Generic;
using System.Security.Cryptography;
using CUE4Parse.UE4.Assets.Exports;
using CUE4Parse.UE4.Assets.Exports.Animation;
using CUE4Parse.UE4.Assets.Objects;
using CUE4Parse.UE4.Objects.Core.i18N;
using CUE4Parse.UE4.Objects.UObject;
using FortnitePorting.Application;
using FortnitePorting;
using FortnitePorting.Exporting;
using FortnitePorting.Exporting.Context;
using FortnitePorting.Exporting.Types;
using Newtonsoft.Json;

[assembly: System.Reflection.AssemblyInformationalVersion("4.3.4")]

internal static class Program
{
    public static async Task<int> Main(string[] args)
    {
        try
        {
            Console.WriteLine("Initializing existing Fortnite Porting services (no settings writes).");
            AppServices.Initialize();
            AppServices.AppSettings.Load();
            AppServices.AppSettings.ShouldSaveOnExit = false;
            // Keep the user's existing cache intact during this separate inspection session.
            AppServices.AppSettings.Developer.ChunkCacheLifetime = int.MaxValue / 100000;
            Console.WriteLine("Assets: " + AppServices.App.AssetsFolder.FullName);
            var parser = AppServices.UEParse;
            parser.PropertyChanged += (_, e) =>
            {
                if (e.PropertyName == "Status" && !parser.Status.StartsWith("Loading ")
                    && !parser.Status.StartsWith("Registering ")) Console.WriteLine(parser.Status);
            };
            await parser.Initialize();
            Console.WriteLine("Parser initialized: " + parser.FinishedLoading);
            Console.WriteLine("Files: " + parser.Provider?.Files.Count);
            var provider = parser.Provider;
            if (!parser.FinishedLoading || provider is null) return 1;
            var reportRoot = args.Length > 0 ? Path.GetFullPath(args[0]) : Path.Combine(Environment.CurrentDirectory, "report");
            var limit = args.Length > 1 ? int.Parse(args[1]) : 3;
            Directory.CreateDirectory(Path.Combine(reportRoot, "assets"));
            if (args.Length > 2 && args[2] == "--export")
                return await ExportSelected(reportRoot, limit);
            var rows = new List<EmoteAudit>();
            foreach (var path in AppServices.AppSettings.Application.FavoriteAssets)
            {
                if (!path.Contains("/Dances/", StringComparison.OrdinalIgnoreCase)) continue;
                if (args.Length > 3 && args[2] == "--inspect-ids"
                    && !new HashSet<string>(args[3].Split(','), StringComparer.OrdinalIgnoreCase)
                        .Contains(path[(path.LastIndexOf('.') + 1)..])) continue;
                if (rows.Count >= limit) break;
                var row = new EmoteAudit { AssetPath = path, Id = path[(path.LastIndexOf('.') + 1)..] };
                rows.Add(row);
                try
                {
                    var asset = provider.LoadPackageObject(path);
                    if (asset is null) throw new InvalidDataException("Emote asset could not be loaded.");
                    row.Name = (asset.GetOrDefault<FText?>("DisplayName")
                        ?? asset.GetOrDefault<FText?>("ItemName"))?.Text ?? row.Id;
                    row.AssetJson = Path.Combine(reportRoot, "assets", row.Id + ".json");
                    File.WriteAllText(row.AssetJson, JsonConvert.SerializeObject(asset, Formatting.Indented));
                    AddVariant(row, "Male Medium", asset.GetOrDefault<UAnimMontage?>("Animation")
                        ?? asset.GetOrDefault<UAnimMontage?>("FrontEndAnimation"));
                    AddVariant(row, "Female Medium", asset.GetOrDefault<UAnimMontage?>("AnimationFemaleOverride"));
                    var overrides = asset.GetOrDefault<FStructFallback[]>("AnimationOverrides", Array.Empty<FStructFallback>());
                    foreach (var item in overrides)
                    {
                        var gender = item.GetOrDefault<FName>("Gender").Text;
                        var body = item.GetOrDefault<FName>("BodyType").Text;
                        row.OverrideLabels.Add(gender + " " + body);
                        if (body.EndsWith("::Medium", StringComparison.Ordinal)
                            || body.EndsWith("::MediumAndSmall", StringComparison.Ordinal))
                        {
                            var overrideMontage = item.GetOrDefault<UAnimMontage?>("EmoteMontage");
                            if (gender.EndsWith("::Male", StringComparison.Ordinal))
                                AddVariant(row, "Male Medium", overrideMontage);
                            else if (gender.EndsWith("::Female", StringComparison.Ordinal))
                                AddVariant(row, "Female Medium", overrideMontage);
                            else row.Errors.Add("Medium override with unsupported gender: " + gender);
                        }
                    }
                    row.Status = row.Variants.Count == 0 ? "unresolved" : "inspected";
                }
                catch (Exception error)
                {
                    row.Status = "unresolved";
                    row.Errors.Add(error.GetType().Name + ": " + error.Message);
                }
                WriteJson(Path.Combine(reportRoot, "audit.json"), rows);
                Console.WriteLine($"[{rows.Count}] {row.Id}: {row.Status}; medium variants={row.Variants.Count}");
            }
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.ToString());
            return 1;
        }
    }

    private static void WriteJson(string path, object value)
    {
        File.WriteAllText(path + ".tmp", JsonConvert.SerializeObject(value, Formatting.Indented));
        File.Move(path + ".tmp", path, true);
    }

    private static async Task<int> ExportSelected(string root, int limit)
    {
        var selection = JsonConvert.DeserializeObject<BatchSelection>(File.ReadAllText(Path.Combine(root, "selection.json")));
        if (selection is null || selection.SourceRevision != "8058810ece4405bfde931d97c72467b07034a881")
            throw new InvalidDataException("Selection source revision does not match this helper.");
        if (selection.AuditSha256 != HashFile(Path.Combine(root, "audit.json")))
            throw new InvalidDataException("The audit changed after classification.");
        var provider = AppServices.UEParse.Provider;
        if (provider is null) throw new InvalidOperationException("No parser provider.");
        var favorites = new HashSet<string>(AppServices.AppSettings.Application.FavoriteAssets, StringComparer.OrdinalIgnoreCase);
        var destination = AppServices.App.AssetsFolder.FullName;
        var stage = Path.Combine(root, "staging");
        Directory.CreateDirectory(stage);
        var recordsPath = Path.Combine(root, "exports.json");
        var records = File.Exists(recordsPath)
            ? JsonConvert.DeserializeObject<List<ExportRecord>>(File.ReadAllText(recordsPath)) ?? new List<ExportRecord>()
            : new List<ExportRecord>();
        var processed = 0;
        foreach (var item in selection.Items)
        {
            if (item.Status != "ready") continue;
            if (processed >= limit) break;
            processed++;
            var record = new ExportRecord { Id = item.Id, Name = item.Name };
            try
            {
                if (!favorites.Contains(item.AssetPath)) throw new InvalidDataException("No longer favorited.");
                if (item.Variants.Count != 2) throw new InvalidDataException("A medium pair is required.");
                if (item.AssetSha256 != HashFile(Path.Combine(root, "assets", item.Id + ".json")))
                    throw new InvalidDataException("Asset evidence changed after classification.");
                var asset = provider.LoadPackageObject(item.AssetPath);
                if (asset is null) throw new InvalidDataException("Emote asset missing.");
                var currentJson = JsonConvert.SerializeObject(asset, Formatting.Indented);
                var currentHash = Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(currentJson))).ToLowerInvariant();
                if (currentHash != item.AssetSha256) throw new InvalidDataException("Live emote metadata differs from the audit.");
                using var meta = AppServices.AppSettings.ExportSettings.CreateExportMeta(EExportLocation.AssetsFolder);
                meta.AssetsRoot = stage;
                meta.CustomPath = null;
                meta.Settings.OpenFoldersOnExport = false;
                foreach (var variant in item.Variants)
                {
                    var currentMontage = variant.Label switch
                    {
                        "Male Medium" => asset.GetOrDefault<UAnimMontage?>("Animation")
                            ?? asset.GetOrDefault<UAnimMontage?>("FrontEndAnimation"),
                        "Female Medium" => asset.GetOrDefault<UAnimMontage?>("AnimationFemaleOverride"),
                        _ => throw new InvalidDataException("Non-medium variant in selection.")
                    };
                    if (currentMontage is null || currentMontage.GetPathName() != variant.MontagePath)
                        throw new InvalidDataException("Medium montage changed or is unavailable: " + variant.Label);
                    var fresh = new VariantAudit { Label = variant.Label, MontagePath = variant.MontagePath };
                    InspectAnimation(currentMontage, fresh, new HashSet<string>(StringComparer.OrdinalIgnoreCase));
                    if (fresh.Errors.Count > 0 || fresh.PropEvidence.Count > 0)
                        throw new InvalidDataException("Animation no longer passes the prop audit.");
                    if (!new HashSet<string>(fresh.AnimationPaths, StringComparer.OrdinalIgnoreCase).SetEquals(variant.AnimationPaths))
                        throw new InvalidDataException("Animation graph changed after inspection.");
                    var export = new AnimExport(item.Name, currentMontage, [], EExportType.Animation, meta, null);
                    await export.WaitForExports();
                    if (export.Props.Count > 0) throw new InvalidDataException("Exporter discovered a prop.");
                    var context = new ExportContext(meta);
                    foreach (var path in variant.AnimationPaths)
                    {
                        if (provider.LoadPackageObject(path) is not UAnimSequence sequence) continue;
                        await context.ExportAsync(sequence);
                    }
                    await Task.WhenAll(context.ExportTasks);
                    var variantRecord = new VariantExportRecord { Label = variant.Label, Montage = variant.MontagePath };
                    record.Variants.Add(variantRecord);
                    foreach (var path in variant.AnimationPaths)
                    {
                        if (provider.LoadPackageObject(path) is not UAnimSequence sequence) continue;
                        var stagedPath = context.GetExportPath(sequence, "ueanim");
                        variantRecord.Files.Add(Publish(stagedPath, stage, destination, "animation"));
                    }
                    foreach (var sound in export.Sounds)
                    {
                        var soundAsset = provider.LoadPackageObject(sound.Path);
                        if (soundAsset is null) throw new InvalidDataException("Exported soundtrack reference missing.");
                        var stagedPath = context.GetExportPath(soundAsset, "wav");
                        variantRecord.Files.Add(Publish(stagedPath, stage, destination, "audio"));
                    }
                    variantRecord.AudioReferences = export.Sounds.Count;
                    if (variantRecord.Files.Count == 0) throw new InvalidDataException("No animation files were produced.");
                }
                record.Status = "complete";
            }
            catch (Exception error)
            {
                record.Status = "failed";
                record.Error = error.GetType().Name + ": " + error.Message;
            }
            records.RemoveAll(previous => previous.Id == record.Id);
            records.Add(record);
            WriteJson(recordsPath, records);
            Console.WriteLine($"EXPORT [{processed}] {record.Name}: {record.Status} {record.Error}");
        }
        return 0;
    }

    private static ExportedFile Publish(string staged, string stageRoot, string destination, string kind)
    {
        var info = new FileInfo(staged);
        if (!info.Exists || info.Length < (kind == "audio" ? 44 : 16))
            throw new InvalidDataException("Export failed to produce a valid-sized " + kind + " file: " + staged);
        if (kind == "animation")
        {
            using var stream = info.OpenRead();
            Span<byte> magic = stackalloc byte[8];
            if (stream.Read(magic) != 8 || !magic.SequenceEqual("UEFORMAT"u8))
                throw new InvalidDataException("Invalid UEFormat animation: " + staged);
        }
        var relative = Path.GetRelativePath(stageRoot, staged);
        if (relative.StartsWith("..") || Path.IsPathRooted(relative)) throw new InvalidDataException("Export path escaped staging.");
        var final = Path.Combine(destination, relative);
        var hash = HashFile(staged);
        var reused = File.Exists(final);
        if (reused && HashFile(final) != hash)
            throw new IOException("Existing file differs; preserved both copies: " + final);
        if (!reused)
        {
            var parent = Path.GetDirectoryName(final);
            if (parent is null) throw new InvalidDataException("Missing output directory.");
            Directory.CreateDirectory(parent);
            var temporary = final + ".batch-tmp";
            File.Copy(staged, temporary, true);
            File.Move(temporary, final, false);
        }
        return new ExportedFile { Kind = kind, Path = final, Sha256 = hash, Bytes = info.Length, Reused = reused };
    }

    private static string HashFile(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static void AddVariant(EmoteAudit row, string label, UAnimMontage? montage)
    {
        if (montage is null) return;
        foreach (var existing in row.Variants)
        {
            if (existing.Label != label) continue;
            if (existing.MontagePath != montage.GetPathName())
                row.Errors.Add("Conflicting medium montage references for " + label);
            return;
        }
        var variant = new VariantAudit { Label = label, MontagePath = montage.GetPathName() };
        row.Variants.Add(variant);
        var visited = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        InspectAnimation(montage, variant, visited);
    }

    private static void InspectAnimation(UAnimSequenceBase animation, VariantAudit result, HashSet<string> visited)
    {
        var path = animation.GetPathName();
        if (!visited.Add(path)) return;
        result.AnimationPaths.Add(path);
        // A list of sequence paths cannot reconstruct montage timing or routing.
        // Preserve parser evidence without interpreting section names as playback order.
        if (animation is UAnimMontage || animation is UAnimComposite)
            result.AnimationGraphs[path] = JsonConvert.SerializeObject(animation, Formatting.None);
        else if (animation is UAnimSequence)
            result.SequenceEvidence[path] = JsonConvert.SerializeObject(animation, Formatting.None);
        if (animation.Notifies is { } notifies)
        {
            foreach (var notify in notifies)
            {
                if (notify is null) { result.Errors.Add("Null notify: " + path); continue; }
                InspectNotify(notify.NotifyStateClass, result, path);
                InspectNotify(notify.Notify, result, path);
                if (notify.NotifyName is { } name && !name.IsNone) result.NamedNotifies.Add(name.Text);
            }
        }
        if (animation is UAnimMontage montage)
        {
            foreach (var slot in montage.SlotAnimTracks)
            {
                if (slot?.AnimTrack?.AnimSegments is not { } segments)
                { result.Errors.Add("Missing montage track: " + path); continue; }
                InspectSegments(segments, result, visited);
            }
            foreach (var section in montage.CompositeSections)
            {
                if (section?.LinkedSequence is not { IsNull: false } reference) continue;
                var linked = reference.Load<UAnimSequenceBase>();
                if (linked is null) result.Errors.Add("Unresolved section sequence: " + path);
                else InspectAnimation(linked, result, visited);
            }
        }
        else if (animation is UAnimComposite composite)
        {
            if (composite.AnimationTrack?.AnimSegments is not { } segments)
                result.Errors.Add("Missing composite track: " + path);
            else InspectSegments(segments, result, visited);
        }
        else if (animation is not UAnimSequence)
            result.Errors.Add("Unsupported animation type: " + animation.ExportType);
    }

    private static void InspectSegments(FAnimSegment[] segments, VariantAudit result, HashSet<string> visited)
    {
        foreach (var segment in segments)
        {
            var reference = segment?.AnimReference;
            if (reference is null || reference.IsNull)
            { result.Errors.Add("Missing animation segment reference"); continue; }
            var linked = reference.Load<UAnimSequenceBase>();
            if (linked is null) result.Errors.Add("Unresolved animation segment");
            else InspectAnimation(linked, result, visited);
        }
    }

    private static void InspectNotify(FPackageIndex? reference, VariantAudit result, string animationPath)
    {
        if (reference is null || reference.IsNull) return;
        var notify = reference.Load();
        if (notify is null) { result.Errors.Add("Unresolved notify: " + animationPath); return; }
        var type = notify.ExportType;
        if (!result.NotifyTypes.Contains(type)) result.NotifyTypes.Add(type);
        if (type.Contains("Prop", StringComparison.OrdinalIgnoreCase))
            result.PropEvidence.Add(type + ": " + notify.GetPathName());
        result.NotifyDetails.Add(JsonConvert.SerializeObject(notify, Formatting.None));
    }
}

internal sealed class EmoteAudit
{
    public string Id = "";
    public string AssetPath = "";
    public string Name = "";
    public string AssetJson = "";
    public string Status = "pending";
    public List<string> OverrideLabels = new();
    public List<string> Errors = new();
    public List<VariantAudit> Variants = new();
}

internal sealed class VariantAudit
{
    public string Label = "";
    public string MontagePath = "";
    public List<string> AnimationPaths = new();
    public Dictionary<string, string> AnimationGraphs = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> SequenceEvidence = new(StringComparer.OrdinalIgnoreCase);
    public List<string> NotifyTypes = new();
    public List<string> NamedNotifies = new();
    public List<string> NotifyDetails = new();
    public List<string> PropEvidence = new();
    public List<string> Errors = new();
}

internal sealed class BatchSelection
{
    public string SourceRevision = "";
    public string AuditSha256 = "";
    public List<SelectedEmote> Items = new();
}

internal sealed class SelectedEmote
{
    public string Id = "";
    public string Name = "";
    public string AssetPath = "";
    public string Status = "";
    public string AssetSha256 = "";
    public List<VariantAudit> Variants = new();
}

internal sealed class ExportRecord
{
    public string Id = "";
    public string Name = "";
    public string Status = "pending";
    public string Error = "";
    public List<VariantExportRecord> Variants = new();
}

internal sealed class VariantExportRecord
{
    public string Label = "";
    public string Montage = "";
    public int AudioReferences;
    public List<ExportedFile> Files = new();
}

internal sealed class ExportedFile
{
    public string Kind = "";
    public string Path = "";
    public string Sha256 = "";
    public long Bytes;
    public bool Reused;
}
