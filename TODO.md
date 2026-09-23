# TODO

## Joinery

Parts are modelled at their visible size, with no joinery. For the shaker table the
aprons' length is the distance between the legs, shoulder to shoulder.

That makes the cut list wrong for any joint that adds material: a tenon on each end
of an apron makes its cut length longer than what's listed. Pocket screws, dowels, and
dominoes don't change the cut length, but mortise & tenon, bridle joints, and dadoes
(for the part that sits in the dado) do.

Once the joints are chosen:

- Model the joints on the parts, so the drawing & the part sizes include them
- The cut list's dimensions come from the part classes' `length`, `width` &
  `thickness` (see `toolbox/cutlist.py`), so they must be the size including the
  joints, while the drawing's dimensions can stay shoulder to shoulder
