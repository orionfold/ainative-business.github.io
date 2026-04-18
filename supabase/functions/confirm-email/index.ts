import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SITE = "https://ainative.business";

function redirect(path: string) {
  return new Response(null, {
    status: 302,
    headers: { Location: `${SITE}${path}` },
  });
}

Deno.serve(async (req) => {
  if (req.method !== "GET") {
    return redirect("/confirmed?status=error&error=Method+not+allowed");
  }

  const url = new URL(req.url);
  const token = url.searchParams.get("token");

  if (!token) {
    return redirect("/confirmed?status=error&error=Invalid+confirmation+link");
  }

  try {
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    );

    // Look up by token
    const { data: row, error: selectError } = await supabase
      .from("waitlist")
      .select("id, email, confirmed")
      .eq("confirm_token", token)
      .maybeSingle();

    if (selectError) {
      console.error("Select error:", selectError);
      return redirect("/confirmed?status=error&error=Something+went+wrong");
    }

    if (!row) {
      return redirect(
        "/confirmed?status=error&error=This+link+has+expired+or+was+already+used",
      );
    }

    if (row.confirmed) {
      return redirect("/confirmed?status=already");
    }

    // Confirm the signup
    const { error: updateError } = await supabase
      .from("waitlist")
      .update({
        confirmed: true,
        confirm_token: null,
        confirmed_at: new Date().toISOString(),
      })
      .eq("id", row.id);

    if (updateError) {
      console.error("Update error:", updateError);
      return redirect("/confirmed?status=error&error=Something+went+wrong");
    }

    return redirect("/confirmed");
  } catch (err) {
    console.error("Unhandled error:", err);
    return redirect("/confirmed?status=error&error=Something+went+wrong");
  }
});
